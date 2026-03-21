"""
Regression tests for audit issue #38.

Scope of this PR:
  Issue #5 — betfair_client.py: division by zero in cashout + weighted avg odds
  Issue #7 — tick_dispatcher.py: pending ticks cleared for both consumers when only one fires

Issues outside this PR's scope:
  #1, #2, #6 — already fixed in base branch (separate evidence documented in PR #50 comment)
  #3, #4     — blocked by pre-existing missing exports in dutching.py
"""

import pytest


# =============================================================================
# Issue #5: betfair_client.py
# FIXED IN THIS PR
#
# Sub-issue A (betfair_client.py:856):
#   cashout_stake = potential_profit / (current_odds - 1)
#   → ZeroDivisionError when current_odds == 1
#
# Sub-issue B (betfair_client.py:905-906):
#   position["back_avg_odds"] = order["averagePriceMatched"] or 0
#   → overwrites on every order; last order wins instead of weighted average
# =============================================================================

class TestIssue5BetfairClientCashout:

    def _make_client(self):
        from betfair_client import BetfairClient
        return BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k2")

    # --- Sub-issue A: division by zero guard ---

    def test_back_cashout_current_odds_exactly_1_returns_zeros(self):
        """
        OLD: potential_profit / (current_odds - 1) → ZeroDivisionError
        NEW: guard returns all-zero dict when current_odds <= 1
        """
        client = self._make_client()
        result = client.calculate_cashout(
            original_stake=100.0,
            original_odds=2.0,
            current_odds=1.0,
            side="BACK",
        )
        assert result["cashout_stake"] == 0.0
        assert result["profit_if_win"] == 0.0
        assert result["profit_if_lose"] == 0.0
        assert result["guaranteed_profit"] == 0.0

    def test_lay_cashout_current_odds_exactly_1_returns_zeros(self):
        """
        OLD: liability / (current_odds - 1) → ZeroDivisionError
        NEW: guard returns all-zero dict when current_odds <= 1
        """
        client = self._make_client()
        result = client.calculate_cashout(
            original_stake=50.0,
            original_odds=3.0,
            current_odds=1.0,
            side="LAY",
        )
        assert result["cashout_stake"] == 0.0

    def test_back_cashout_current_odds_below_1_returns_zeros(self):
        """current_odds < 1 (invalid odds) handled without crash."""
        client = self._make_client()
        result = client.calculate_cashout(
            original_stake=100.0,
            original_odds=2.0,
            current_odds=0.5,
            side="BACK",
        )
        assert result["cashout_stake"] == 0.0

    def test_back_cashout_normal_odds_no_regression(self):
        """Normal BACK cashout path produces the correct value unchanged."""
        client = self._make_client()
        result = client.calculate_cashout(
            original_stake=100.0,
            original_odds=3.0,
            current_odds=2.0,
            side="BACK",
        )
        # potential_profit = 100 * (3-1) = 200
        # cashout_stake    = 200 / (2-1) = 200
        assert result["cashout_stake"] == pytest.approx(200.0, abs=0.01)

    # --- Sub-issue B: weighted average odds ---

    def test_get_position_weighted_avg_odds_two_back_orders(self, monkeypatch):
        """
        OLD: back_avg_odds overwritten on every order → last order wins
             Two orders (100@2.0, 200@3.0) → back_avg_odds = 3.0  (wrong)
        NEW: stake-weighted average
             (100×2.0 + 200×3.0) / 300 = 2.6667
        """
        from betfair_client import BetfairClient
        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k2")
        client.client = object()  # satisfy `if not self.client` guard

        fake_orders = {
            "matched": [
                {"selectionId": 99, "side": "BACK", "sizeMatched": 100.0, "averagePriceMatched": 2.0},
                {"selectionId": 99, "side": "BACK", "sizeMatched": 200.0, "averagePriceMatched": 3.0},
            ],
            "partiallyMatched": [],
        }
        monkeypatch.setattr(client, "get_current_orders", lambda **kw: fake_orders)
        monkeypatch.setattr(client, "get_market_profit_and_loss", lambda mids: {})

        pos = client.get_position("1.234", 99)

        expected = (100.0 * 2.0 + 200.0 * 3.0) / 300.0  # 2.6667
        assert pos["back_avg_odds"] == pytest.approx(expected, rel=1e-6), (
            f"Expected weighted avg {expected:.4f}, got {pos['back_avg_odds']:.4f} "
            f"(old code returned 3.0)"
        )
        assert pos["back_stake"] == pytest.approx(300.0)

    def test_get_position_single_order_no_regression(self, monkeypatch):
        """Single order: weighted average degenerates to the order's own odds."""
        from betfair_client import BetfairClient
        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k2")
        client.client = object()

        fake_orders = {
            "matched": [
                {"selectionId": 7, "side": "LAY", "sizeMatched": 50.0, "averagePriceMatched": 4.5},
            ],
            "partiallyMatched": [],
        }
        monkeypatch.setattr(client, "get_current_orders", lambda **kw: fake_orders)
        monkeypatch.setattr(client, "get_market_profit_and_loss", lambda mids: {})

        pos = client.get_position("1.999", 7)
        assert pos["lay_avg_odds"] == pytest.approx(4.5)
        assert pos["lay_stake"] == pytest.approx(50.0)


# =============================================================================
# Issue #7: tick_dispatcher.py
# FIXED IN THIS PR
#
# Buggy line (tick_dispatcher.py:155-156 original):
#   if should_update_ui or should_check_automation:
#       self._pending_ticks.clear()
#
# When only one consumer fires, this cleared the shared buffer for both,
# starving the other consumer of its pending ticks.
#
# Fixed (tick_dispatcher.py:149, 155):
#   if should_update_ui:
#       ...
#       self._pending_ticks.clear()   ← only when UI actually fired
#   if should_check_automation:
#       ...
#       self._pending_ticks.clear()   ← only when automation actually fired
# =============================================================================

class TestIssue7TickDispatcherIndependentClearing:

    def test_ui_only_dispatch_does_not_starve_automation(self, monkeypatch):
        """
        Scenario: UI fires (t=0.30 >= 0.25 interval), automation does NOT
                  (0.30 - last_automation=0.25 = 0.05 < 0.10 interval).

        OLD: _pending_ticks.clear() ran because (UI || auto) was True
             → automation's next cycle started from empty buffer (starved)
        NEW: clear only runs inside `if should_update_ui`
             → automation accumulates ticks until its own interval elapses
             → automation_dispatch_count stays 0 after this tick
        """
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        ui_received = []
        auto_received = []
        dispatcher.register_ui_callback(lambda t: ui_received.append(dict(t)))
        dispatcher.register_automation_callback(lambda t: auto_received.append(dict(t)))

        # Force known state: UI last fired at 0.0, automation last fired at 0.25
        # so at t=0.30: UI elapsed=0.30 >= 0.25 ✓, automation elapsed=0.05 < 0.10 ✗
        dispatcher._last_ui_update = 0.0
        dispatcher._last_automation_check = 0.25

        times = iter([0.30])
        monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

        dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=1, timestamp=0.30))

        assert len(ui_received) == 1,   "UI should have fired exactly once"
        assert len(auto_received) == 0, "automation must NOT fire — it has only 0.05s elapsed"
        stats = dispatcher.get_stats()
        assert stats["ui_dispatches"] == 1
        assert stats["automation_dispatches"] == 0

    def test_automation_only_dispatch_does_not_starve_ui(self, monkeypatch):
        """
        Scenario: automation fires (t=0.12 >= 0.10), UI does NOT (0.12 < 0.25).

        OLD: clear() ran → UI's next cycle saw an empty buffer
        NEW: clear() only runs inside `if should_check_automation`
             → UI still fires on its own interval and receives its own snapshot
        """
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        ui_received = []
        auto_received = []
        dispatcher.register_ui_callback(lambda t: ui_received.append(dict(t)))
        dispatcher.register_automation_callback(lambda t: auto_received.append(dict(t)))

        dispatcher._last_ui_update = 0.0
        dispatcher._last_automation_check = 0.0

        times = iter([0.12, 0.50])
        monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

        # t=0.12: automation fires, UI does not
        dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=10, timestamp=0.12))
        assert len(auto_received) == 1, "automation should have fired"
        assert len(ui_received) == 0,   "UI must not fire yet"

        # t=0.50: UI now fires on its own interval (0.50 >= 0.25)
        dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=11, timestamp=0.50))
        assert len(ui_received) == 1, "UI should fire at t=0.50"

    def test_both_consumers_receive_same_snapshot(self, monkeypatch):
        """
        When both UI and automation fire simultaneously, both receive the
        same snapshot — dual-consumer behavior is unaffected by the fix.
        """
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        ui_batches = []
        auto_batches = []
        dispatcher.register_ui_callback(
            lambda t: ui_batches.append(set(k[1] for k in t))
        )
        dispatcher.register_automation_callback(
            lambda t: auto_batches.append(set(k[1] for k in t))
        )

        dispatcher._last_ui_update = 0.0
        dispatcher._last_automation_check = 0.0

        times = iter([1.0])
        monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

        dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=42, timestamp=1.0))

        assert ui_batches == [{42}],   f"UI received: {ui_batches}"
        assert auto_batches == [{42}], f"auto received: {auto_batches}"

    def test_pending_buffer_empty_after_ui_dispatch(self, monkeypatch):
        """
        After UI fires and clears, the buffer is empty.
        Automation (pinned to never-fire) does not interfere.
        """
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        dispatcher._last_ui_update = 0.0
        dispatcher._last_automation_check = 999.0  # effectively disabled

        times = iter([0.30])
        monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

        dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=1, timestamp=0.30))

        with dispatcher._lock:
            pending = len(dispatcher._pending_ticks)
        assert pending == 0, f"Buffer should be empty after UI dispatch; got {pending}"

    def test_total_ticks_stat_unaffected(self, monkeypatch):
        """total_ticks counter is not regressed by the fix."""
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        times = iter([0.0, 0.1, 0.2, 0.3, 0.4])
        monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

        for i in range(5):
            dispatcher.dispatch_tick(
                TickData(market_id="1.1", selection_id=i, timestamp=float(i))
            )

        assert dispatcher.get_stats()["total_ticks"] == 5
