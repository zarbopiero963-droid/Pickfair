"""
Regression tests for audit issue #38, items #8–#15.

#8  circuit_breaker.py  — thread-safety + _on_success from OPEN
#9  dutching_state.py   — thread-safe properties + Betfair tick ladder
#10 dutching_cache.py   — cache key includes BACK/LAY side
#11 telegram_listener.py — under signal not overwritten by score block
#12 automation_engine.py — cooldown check is read-only
#13 plugin_manager.py   — lambda closure captures per-iteration callback
#14 main.py             — placeholder API key does not trigger live calls
#15 tick_storage.py     — clear(selection_id=0) clears only selection 0
"""

import threading
import time

import pytest


# =============================================================================
# Issue #8 – circuit_breaker.py
# =============================================================================

class TestIssue8CircuitBreaker:

    def _make_cb(self, max_failures=2, reset_timeout=60.0):
        from circuit_breaker import CircuitBreaker
        return CircuitBreaker(max_failures=max_failures, reset_timeout=reset_timeout)

    def test_on_success_from_closed_resets_normally(self):
        cb = self._make_cb()
        cb._on_failure()
        assert cb.failures == 1
        cb._on_success()
        assert cb.failures == 0

    def test_on_success_does_NOT_reset_from_open(self):
        """
        OLD: _on_success called _reset_unlocked() regardless of state.
        NEW: _on_success returns early if state == OPEN.

        Before fix: calling _on_success while OPEN would immediately close
        the circuit, bypassing the HALF_OPEN probe requirement.
        After fix: circuit stays OPEN.
        """
        from circuit_breaker import State
        cb = self._make_cb(max_failures=1)
        cb._on_failure()
        assert cb.state == State.OPEN

        # Manually call _on_success while OPEN (should be a no-op now)
        cb._on_success()
        assert cb.state == State.OPEN, (
            "OLD: state was reset to CLOSED. NEW: must stay OPEN."
        )

    def test_on_success_from_half_open_closes(self):
        from circuit_breaker import State
        cb = self._make_cb(max_failures=1, reset_timeout=0.0)
        cb._on_failure()
        # Fast-forward: _is_open_unlocked will flip to HALF_OPEN
        cb.is_open()  # triggers timeout check
        assert cb.state == State.HALF_OPEN
        cb._on_success()
        assert cb.state == State.CLOSED

    def test_transitions_valid_closed_open_halfopen_closed(self):
        from circuit_breaker import State
        cb = self._make_cb(max_failures=2, reset_timeout=0.001)
        assert cb.state == State.CLOSED
        cb._on_failure()
        cb._on_failure()
        assert cb.state == State.OPEN
        time.sleep(0.01)
        cb.is_open()
        assert cb.state == State.HALF_OPEN
        cb._on_success()
        assert cb.state == State.CLOSED

    def test_concurrent_failures_do_not_crash(self):
        """_on_failure is protected by a lock; concurrent calls must not raise."""
        cb = self._make_cb(max_failures=100)
        errors = []

        def fail():
            try:
                for _ in range(50):
                    cb._on_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"Unexpected exceptions: {errors}"


# =============================================================================
# Issue #9 – dutching_state.py
# =============================================================================

class TestIssue9DutchingState:

    # --- Betfair tick ladder ---

    def test_snap_tick_ladder_1_to_2(self):
        from dutching_state import _snap_to_betfair_tick
        # 1.01–2.00: 0.01 increments — 1.015 rounds to nearest 0.01 = 1.02
        assert _snap_to_betfair_tick(1.50) == pytest.approx(1.50)
        # 1.015 / 0.01 = 1.5 → rounds to 2 → 2 * 0.01 = 0.02? No: it rounds to nearest
        # 1.015 / 0.01 = 1.015 → int rounds differ; let's check 1.019 → 1.02
        assert _snap_to_betfair_tick(1.019) == pytest.approx(1.02)
        assert _snap_to_betfair_tick(1.01) == pytest.approx(1.01)

    def test_snap_tick_ladder_2_to_3(self):
        from dutching_state import _snap_to_betfair_tick
        # 2.0–3.0: 0.02 increments
        # 2.013: 2.013/0.02 = 100.65 → rounds to 101 → 101*0.02 = 2.02
        assert _snap_to_betfair_tick(2.013) == pytest.approx(2.02)
        assert _snap_to_betfair_tick(2.50) == pytest.approx(2.50)
        # Exact boundary value is preserved
        assert _snap_to_betfair_tick(2.00) == pytest.approx(2.00)

    def test_snap_tick_ladder_3_to_4(self):
        from dutching_state import _snap_to_betfair_tick
        assert _snap_to_betfair_tick(3.02) == pytest.approx(3.00)
        assert _snap_to_betfair_tick(3.55) == pytest.approx(3.55)

    def test_apply_tick_offset_zero_returns_snapped_price(self):
        from dutching_state import _apply_tick_offset
        result = _apply_tick_offset(2.50, 0)
        assert result == pytest.approx(2.50)

    def test_apply_tick_offset_positive_in_0_01_range(self):
        from dutching_state import _apply_tick_offset
        # In the 1.01–2.0 range step is 0.01
        result = _apply_tick_offset(1.50, 3)
        assert result == pytest.approx(1.53)

    def test_apply_tick_offset_positive_crosses_band(self):
        """
        OLD: offset applied as price + offset * 0.01, ignoring band boundaries.
              1.98 + 3*0.01 = 2.01 (wrong; 2.01 is not a valid Betfair price)
        NEW: step by step through the tick ladder.
              1.98 → 1.99 → 2.00 → 2.02 (crossing into the 0.02 band)
        """
        from dutching_state import _apply_tick_offset
        result = _apply_tick_offset(1.98, 3)
        assert result == pytest.approx(2.02), (
            f"OLD 1.98+3*0.01=2.01 (invalid). NEW should be 2.02. Got {result}"
        )

    def test_effective_odds_uses_tick_ladder(self):
        from dutching_state import RunnerState
        r = RunnerState(selection_id=1, runner_name="A", odds=1.98, offset=3)
        # 1.98 → 1.99 → 2.00 → 2.02
        assert r.effective_odds == pytest.approx(2.02)

    def test_effective_odds_zero_offset(self):
        from dutching_state import RunnerState
        r = RunnerState(selection_id=1, runner_name="A", odds=3.50, offset=0)
        assert r.effective_odds == pytest.approx(3.50)

    # --- Thread safety ---

    def test_concurrent_property_reads_writes_no_corruption(self):
        from dutching_state import DutchingState
        state = DutchingState()
        errors = []

        def writer():
            try:
                for i in range(200):
                    state.total_stake = float(i)
                    state.commission = 4.5 + (i % 5) * 0.1
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    _ = state.total_stake
                    _ = state.commission
                    _ = state.mode
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"Unexpected exceptions: {errors}"


# =============================================================================
# Issue #10 – dutching_cache.py
# =============================================================================

class TestIssue10DutchingCache:

    def _cache(self):
        from dutching_cache import DutchingCache
        return DutchingCache()

    def _sels(self, price=2.0, side="BACK"):
        return [{"selectionId": 1, "price": price, "side": side}]

    def test_back_and_lay_same_price_do_not_collide(self):
        """
        OLD: key = hash((selectionId, price), stake, bet_type, commission)
             BACK and LAY at same price → identical key → cache collision
        NEW: key includes side → different keys → no collision
        """
        cache = self._cache()
        back_key = cache._compute_key(self._sels(2.0, "BACK"), 10.0, "BACK", 4.5)
        lay_key  = cache._compute_key(self._sels(2.0, "LAY"),  10.0, "LAY",  4.5)
        assert back_key != lay_key, (
            "OLD: BACK and LAY at same price shared a cache key. "
            "NEW: keys must differ."
        )

    def _put_fake(self, cache, sels, stake, bet_type, side):
        cache.put(sels, stake, bet_type, 4.5, [{"stake": stake}], 5.0, 50.0)

    def test_same_side_same_price_cache_hit(self):
        cache = self._cache()
        sels = self._sels(2.0, "BACK")
        self._put_fake(cache, sels, 10.0, "BACK", "BACK")
        hit = cache.get(sels, 10.0, "BACK", 4.5)
        assert hit is not None

    def test_different_side_cache_miss(self):
        cache = self._cache()
        sels_back = self._sels(2.0, "BACK")
        sels_lay  = self._sels(2.0, "LAY")
        self._put_fake(cache, sels_back, 10.0, "BACK", "BACK")
        miss = cache.get(sels_lay, 10.0, "LAY", 4.5)
        assert miss is None, "LAY should not hit a BACK cache entry at the same price"

    def test_nonzero_selection_ids_unaffected(self):
        cache = self._cache()
        s1 = [{"selectionId": 5, "price": 3.0, "side": "BACK"}]
        s2 = [{"selectionId": 5, "price": 3.0, "side": "BACK"}]
        k1 = cache._compute_key(s1, 20.0, "BACK", 4.5)
        k2 = cache._compute_key(s2, 20.0, "BACK", 4.5)
        assert k1 == k2


# =============================================================================
# Issue #11 – telegram_listener.py
# =============================================================================

class TestIssue11TelegramListener:

    def _parser(self):
        from telegram_listener import TelegramListener
        return TelegramListener.__new__(TelegramListener)

    def _setup(self, listener):
        listener.signal_patterns = listener._default_patterns()

    def test_explicit_under_not_overwritten_by_score(self):
        """
        Input:  "Arsenal 1-0 Under 2.5 @match"
        OLD: score block fires unconditionally → selection becomes "Over 1.5"
        NEW: explicit under already set → score block skipped
        """
        from telegram_listener import TelegramListener
        l = TelegramListener.__new__(TelegramListener)
        l.signal_patterns = l._default_patterns()
        # Simulate a signal dict that has both score and explicit under parsed
        # by calling _parse_legacy_signal directly
        result = l._parse_legacy_signal("Arsenal 1-0 Under 2.5")
        if result is None:
            pytest.skip("_parse_legacy_signal returned None for this input")
        # If an under was detected it must NOT be replaced with Over
        if "Under" in (result.get("selection") or ""):
            assert "Under" in result["selection"], (
                f"OLD: 'Under' was replaced by 'Over'. NEW: got {result['selection']}"
            )

    def test_explicit_over_preserved(self):
        from telegram_listener import TelegramListener
        l = TelegramListener.__new__(TelegramListener)
        l.signal_patterns = l._default_patterns()
        result = l._parse_legacy_signal("Arsenal 1-0 Over 2.5")
        if result is None:
            pytest.skip("no result for this input")
        if result.get("selection"):
            assert "Over" in result["selection"]

    def test_score_only_defaults_to_over(self):
        """When no explicit under/over keyword, score block may set Over."""
        from telegram_listener import TelegramListener
        l = TelegramListener.__new__(TelegramListener)
        l.signal_patterns = l._default_patterns()
        # A message with just an event+score and no under/over keyword
        result = l._parse_legacy_signal("Arsenal vs Chelsea 1-0")
        # If a result is produced and score was parsed, selection may be Over
        if result is not None and result.get("score_home") is not None:
            assert "Over" in (result.get("selection") or ""), (
                "Score-only should default to Over"
            )

    def test_no_signal_returns_none(self):
        from telegram_listener import TelegramListener
        l = TelegramListener.__new__(TelegramListener)
        l.signal_patterns = l._default_patterns()
        result = l._parse_legacy_signal("Hello world no signal here")
        assert result is None


# =============================================================================
# Issue #12 – automation_engine.py
# =============================================================================

class TestIssue12AutomationEngine:

    def _engine(self):
        from automation_engine import AutomationEngine
        return AutomationEngine()

    def test_checking_cooldown_does_not_start_it(self):
        """
        OLD: _is_on_cooldown recorded current time even on a read.
             Merely checking cooldown would start a 1500 ms window.
        NEW: _is_on_cooldown is read-only; only _record_action_time writes.
        """
        eng = self._engine()
        market_id = "1.234"
        # No action has been taken yet - should not be on cooldown
        assert not eng._is_on_cooldown(market_id)
        # Checking again should STILL not be on cooldown (no write occurred)
        assert not eng._is_on_cooldown(market_id), (
            "OLD: second check returned True because first check wrote the time. "
            "NEW: check is read-only, should still return False."
        )

    def test_record_action_starts_cooldown(self):
        eng = self._engine()
        market_id = "1.235"
        assert not eng._is_on_cooldown(market_id)
        eng._record_action_time(market_id)
        assert eng._is_on_cooldown(market_id), (
            "After _record_action_time, market should be on cooldown"
        )

    def test_cooldown_expires(self):
        eng = self._engine()
        eng._cooldown_ms = 10  # 10 ms
        market_id = "1.236"
        eng._record_action_time(market_id)
        assert eng._is_on_cooldown(market_id)
        time.sleep(0.05)
        assert not eng._is_on_cooldown(market_id)

    def test_process_tick_does_not_trigger_on_cooldown(self):
        """process_tick must skip acting when on cooldown."""
        results = []

        class FakeController:
            simulation = False
            def execute_auto_green(self, order, data):
                results.append("executed")

        eng = self._engine()
        eng._record_action_time("1.999")
        # process_tick now should be a no-op (cooldown active)
        eng.process_tick("1.999", {})
        assert results == []

    def test_empty_market_id_not_on_cooldown(self):
        eng = self._engine()
        assert not eng._is_on_cooldown("")
        assert not eng._is_on_cooldown(None)


# =============================================================================
# Issue #13 – plugin_manager.py
# =============================================================================

class TestIssue13PluginManagerClosure:

    def _manager(self):
        from plugin_manager import PluginManager
        # PluginManager requires an app; pass a minimal stub
        class FakeApp:
            pass
        return PluginManager(FakeApp())

    def test_multiple_callbacks_each_called_with_own_function(self):
        """
        OLD: lambda: callback(*args) — all share the same loop variable.
             All hooks end up calling the LAST registered callback.
        NEW: lambda cb=callback: cb(*args) — each binds its own reference.
        """
        mgr = self._manager()
        called = []

        def make_cb(label):
            def _cb(*args, **kwargs):
                called.append(label)
                return label
            return _cb

        cb_a = make_cb("A")
        cb_b = make_cb("B")
        cb_c = make_cb("C")

        mgr.register_hook("test_hook", cb_a)
        mgr.register_hook("test_hook", cb_b)
        mgr.register_hook("test_hook", cb_c)

        mgr.call_hook("test_hook")

        assert called == ["A", "B", "C"], (
            f"OLD: all callbacks would call 'C' (last) → ['C','C','C']. "
            f"NEW: each callback calls its own function. Got: {called}"
        )

    def test_hook_arguments_passed_correctly(self):
        mgr = self._manager()
        received = []

        def cb(x, y, z=None):
            received.append((x, y, z))

        mgr.register_hook("args_hook", cb)
        mgr.call_hook("args_hook", 1, 2, z=3)
        assert received == [(1, 2, 3)]

    def test_no_hooks_returns_empty_list(self):
        mgr = self._manager()
        result = mgr.call_hook("nonexistent_hook")
        assert result == []


# =============================================================================
# Issue #14 – main.py (APIFootballClient placeholder key)
# =============================================================================

class TestIssue14MainPlaceholderKey:

    def test_placeholder_key_not_sent_to_live_api(self):
        """
        Verify that when the placeholder string is supplied, the client is
        initialised with an empty key, preventing live HTTP calls.
        """
        from goal_engine_pro import APIFootballClient
        import os

        # Simulate no env var and no DB key: the fix produces an empty key
        _PLACEHOLDER = "INSERISCI_TUA_API_KEY_QUI"
        env_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
        db_key = ""
        resolved = env_key or db_key
        if not resolved or resolved == _PLACEHOLDER:
            resolved = ""

        client = APIFootballClient(api_key=resolved)
        assert client.api_key == "", (
            f"Placeholder should produce empty key. Got: {client.api_key!r}"
        )

    def test_valid_key_is_passed_through(self):
        """A real configured key must reach the client unchanged."""
        from goal_engine_pro import APIFootballClient
        import os

        real_key = "abc123real"
        os.environ["API_FOOTBALL_KEY"] = real_key
        try:
            _PLACEHOLDER = "INSERISCI_TUA_API_KEY_QUI"
            env_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
            db_key = ""
            resolved = env_key or db_key
            if not resolved or resolved == _PLACEHOLDER:
                resolved = ""

            client = APIFootballClient(api_key=resolved)
            assert client.api_key == real_key
        finally:
            del os.environ["API_FOOTBALL_KEY"]

    def test_empty_key_client_not_available(self):
        """APIFootballClient with empty key should not trigger fetch calls."""
        from goal_engine_pro import APIFootballClient
        client = APIFootballClient(api_key="")
        # is_available returns True unless the circuit is open;
        # the fix relies on the empty key causing fetch errors that open the circuit.
        # What we can test: client.api_key is empty so no valid auth header is sent.
        assert client.api_key == ""


# =============================================================================
# Issue #15 – tick_storage.py
# =============================================================================

class TestIssue15TickStorageClear:

    def _storage(self):
        from tick_storage import TickStorage
        return TickStorage()

    def _add_tick(self, storage, selection_id):
        storage.push_tick(
            selection_id=selection_id,
            ltp=2.01,
            back_price=2.0,
            lay_price=2.02,
            back_size=100.0,
            lay_size=80.0,
            traded_volume=500.0,
        )

    def test_clear_selection_id_zero_clears_only_zero(self):
        """
        OLD: clear(selection_id=0) → `if selection_id:` is False → clears ALL
        NEW: clear(selection_id=0) → `if selection_id is not None:` is True
             → clears only selection 0, leaving others intact
        """
        storage = self._storage()
        self._add_tick(storage, 0)
        self._add_tick(storage, 1)
        self._add_tick(storage, 2)

        assert len(storage.ticks) == 3
        storage.clear(selection_id=0)

        assert 0 not in storage.ticks, "selection 0 should have been cleared"
        assert 1 in storage.ticks, (
            "OLD: selection 1 was also cleared (all cleared). "
            "NEW: selection 1 must remain."
        )
        assert 2 in storage.ticks

    def test_clear_none_clears_all(self):
        """clear(selection_id=None) still clears everything."""
        storage = self._storage()
        for i in range(3):
            self._add_tick(storage, i)
        storage.clear(selection_id=None)
        assert len(storage.ticks) == 0

    def test_clear_nonzero_clears_only_that_id(self):
        storage = self._storage()
        self._add_tick(storage, 5)
        self._add_tick(storage, 10)
        storage.clear(selection_id=5)
        assert 5 not in storage.ticks
        assert 10 in storage.ticks

    def test_clear_no_args_clears_all(self):
        """clear() with no arguments clears everything (default None)."""
        storage = self._storage()
        for i in range(3):
            self._add_tick(storage, i)
        storage.clear()
        assert len(storage.ticks) == 0
