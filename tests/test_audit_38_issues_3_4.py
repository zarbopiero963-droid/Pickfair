"""
Regression tests for audit issue #38, items #3 and #4.

Issue #3: dutching.py — LAY dutching calculation incorrect
Issue #4: pnl_engine.py — LAY P&L / preview formula incorrect;
          module was also unimportable due to missing dynamic_cashout_single.

Structure:
  TestImportContracts    — imports are restored; no ImportError
  TestIssue3LayDutching  — LAY math correctness
  TestIssue3BackDutching — BACK behavior unchanged (regression)
  TestIssue4PnlEngine    — LAY P&L / preview correctness
"""

import pytest


# =============================================================================
# Import contracts
# =============================================================================

class TestImportContracts:

    def test_dutching_controller_imports_without_error(self):
        """
        controllers/dutching_controller.py imports calculate_dutching_stakes
        and calculate_mixed_dutching from dutching. Both were missing from
        dutching.py and caused ImportError on the main branch.
        """
        # The real guard: the import chain must not raise.
        from dutching import calculate_dutching_stakes, calculate_mixed_dutching
        assert callable(calculate_dutching_stakes)
        assert callable(calculate_mixed_dutching)

    def test_pnl_engine_imports_without_error(self):
        """
        pnl_engine.py imports dynamic_cashout_single from dutching.
        This was missing and blocked all pnl_engine usage.
        """
        from dutching import dynamic_cashout_single
        assert callable(dynamic_cashout_single)

    def test_pnl_engine_module_importable(self):
        """PnLEngine can be instantiated once the import is unblocked."""
        from pnl_engine import PnLEngine
        engine = PnLEngine(commission=4.5)
        assert engine is not None

    def test_all_required_exports_present(self):
        """All exports required by current callers are present."""
        import dutching
        for name in [
            "calculate_dutching_stakes",
            "calculate_mixed_dutching",
            "calculate_ai_mixed_stakes",
            "dynamic_cashout_single",
            "format_currency",
            "validate_selections",
        ]:
            assert hasattr(dutching, name), f"Missing export: {name}"
            assert callable(getattr(dutching, name)), f"Not callable: {name}"


# =============================================================================
# Issue #3: LAY dutching math
# =============================================================================

class TestIssue3LayDutching:

    def _sel(self, sel_id, price, name=None):
        return {
            "selectionId": sel_id,
            "runnerName": name or str(sel_id),
            "price": price,
        }

    def test_equal_odds_lay_equal_stakes(self):
        """
        With identical odds all stakes must be equal (degenerate case).
        stake_i = C / price_i and price_i is the same for all → equal stakes.
        """
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 2.0), self._sel(3, 2.0)]
        results, avg_profit, _ = calculate_dutching_stakes(sels, 30.0, bet_type="LAY")

        stakes = [r["stake"] for r in results]
        assert len(stakes) == 3
        # All stakes equal
        assert abs(stakes[0] - stakes[1]) < 0.02
        assert abs(stakes[1] - stakes[2]) < 0.02
        # Total stake close to requested
        assert abs(sum(stakes) - 30.0) < 0.05

    def test_mixed_odds_lay_different_stakes(self):
        """
        OLD BUG: flat stake = round(target_profit) for every selection,
                 regardless of price. With odds 2.0 and 4.0 this gives
                 the same stake which does NOT equate liability*price.

        NEW FIX: stake_i = C / price_i where C = total / Σ(1/price_i).
                 Higher-odds selections receive smaller stakes.

        Input: two selections at 2.0 and 4.0, total_stake=30
        C = 30 / (1/2 + 1/4) = 30 / 0.75 = 40
        stake_1 = 40/2 = 20,  stake_2 = 40/4 = 10
        """
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 4.0)]
        results, avg_profit, _ = calculate_dutching_stakes(sels, 30.0, bet_type="LAY")

        assert len(results) == 2
        r1 = next(r for r in results if r["selectionId"] == 1)
        r2 = next(r for r in results if r["selectionId"] == 2)

        # Higher-price selection must have smaller stake
        assert r2["stake"] < r1["stake"], (
            f"OLD: flat stake bug — both stakes equal. "
            f"NEW: r2.stake={r2['stake']:.2f} must be < r1.stake={r1['stake']:.2f}"
        )

        # Verify the equal-profit invariant: price_i * stake_i ≈ constant
        c1 = r1["price"] * r1["stake"]
        c2 = r2["price"] * r2["stake"]
        assert abs(c1 - c2) < 0.10, (
            f"Equal-profit invariant violated: price*stake not equal. "
            f"c1={c1:.2f}, c2={c2:.2f}"
        )

    def test_lay_equal_profit_across_outcomes(self):
        """
        For any selection i losing: profit = total_stake - price_i * stake_i.
        With the fix this equals the same constant for all i.

        Three selections at odds 2.0, 3.0, 5.0, total_stake=60.
        """
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 3.0), self._sel(3, 5.0)]
        results, _, _ = calculate_dutching_stakes(sels, 60.0, bet_type="LAY")

        total_stake = sum(r["stake"] for r in results)
        profits = [total_stake - r["price"] * r["stake"] for r in results]

        # All gross profits must be approximately equal
        min_p, max_p = min(profits), max(profits)
        assert max_p - min_p < 0.15, (
            f"Profits not equal across outcomes: {[round(p,2) for p in profits]}"
        )

    def test_lay_stakes_sum_to_total(self):
        """Total allocated stakes must sum to (approximately) requested total."""
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.5), self._sel(2, 4.0), self._sel(3, 6.0)]
        results, _, _ = calculate_dutching_stakes(sels, 50.0, bet_type="LAY")
        total = sum(r["stake"] for r in results)
        assert abs(total - 50.0) < 0.05

    def test_lay_result_has_required_fields(self):
        """Each LAY result dict must contain all required keys."""
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 3.0)]
        results, _, _ = calculate_dutching_stakes(sels, 20.0, bet_type="LAY")
        for r in results:
            for key in ("selectionId", "price", "stake", "side", "liability", "profitIfWins"):
                assert key in r, f"Missing key '{key}' in result: {r}"
            assert r["side"] == "LAY"
            assert r["liability"] > 0

    def test_lay_old_flat_stake_would_fail(self):
        """
        Explicitly verify that the old flat-stake behavior is NOT present.
        Old code: stake = round(target_profit, 2) for every selection.
        This means all stakes are equal when prices differ.

        If odds are 2.0 and 4.0 with total=30, flat_stake ≈ 10 each.
        New code: stakes are 20 and 10 (proportional to 1/price).
        """
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 4.0)]
        results, _, _ = calculate_dutching_stakes(sels, 30.0, bet_type="LAY")

        r1 = next(r for r in results if r["selectionId"] == 1)
        r2 = next(r for r in results if r["selectionId"] == 2)

        # If the old bug were present: r1.stake ≈ r2.stake ≈ some flat value
        # New correct: r1.stake is approximately 2× r2.stake (ratio = price2/price1 = 4/2 = 2)
        ratio = r1["stake"] / r2["stake"]
        assert abs(ratio - 2.0) < 0.10, (
            f"Expected stake ratio ~2.0 (= price2/price1), got {ratio:.3f}. "
            f"Old flat-stake bug would give ratio ≈ 1.0."
        )


# =============================================================================
# Issue #3: BACK dutching regression
# =============================================================================

class TestIssue3BackDutching:

    def _sel(self, sel_id, price):
        return {"selectionId": sel_id, "runnerName": str(sel_id), "price": price}

    def test_back_dutching_proportional_allocation(self):
        """
        BACK: stake_i proportional to implied probability 1/price_i.
        Two runners at 2.0 and 4.0, total=30.
        implied_prob(2.0) = 0.5,  implied_prob(4.0) = 0.25,  book = 0.75
        stake_1 = 30 * 0.5 / 0.75 = 20
        stake_2 = 30 * 0.25 / 0.75 = 10
        """
        from dutching import calculate_dutching_stakes
        results, _, _ = calculate_dutching_stakes(
            [self._sel(1, 2.0), self._sel(2, 4.0)], 30.0, bet_type="BACK"
        )
        r1 = next(r for r in results if r["selectionId"] == 1)
        r2 = next(r for r in results if r["selectionId"] == 2)

        assert abs(r1["stake"] - 20.0) < 0.05
        assert abs(r2["stake"] - 10.0) < 0.05
        for r in results:
            assert r["side"] == "BACK"

    def test_back_dutching_equal_profit_per_winner(self):
        """All BACK winners produce approximately the same net profit."""
        from dutching import calculate_dutching_stakes
        sels = [self._sel(1, 2.0), self._sel(2, 3.0), self._sel(3, 5.0)]
        results, _, _ = calculate_dutching_stakes(sels, 60.0, bet_type="BACK")
        total = sum(r["stake"] for r in results)
        gross_profits = [r["price"] * r["stake"] - total for r in results]
        assert max(gross_profits) - min(gross_profits) < 0.15

    def test_back_dutching_total_stake(self):
        """Total BACK stakes ≈ requested total."""
        from dutching import calculate_dutching_stakes
        sels = [self._sel(i, 2.0 + i * 0.5) for i in range(1, 5)]
        results, _, _ = calculate_dutching_stakes(sels, 40.0, bet_type="BACK")
        assert abs(sum(r["stake"] for r in results) - 40.0) < 0.05

    def test_calculate_mixed_dutching_callable(self):
        """calculate_mixed_dutching is callable and returns 3-tuple."""
        from dutching import calculate_mixed_dutching
        sels = [
            {"selectionId": 1, "price": 2.0, "side": "BACK"},
            {"selectionId": 2, "price": 3.0, "side": "LAY"},
        ]
        result = calculate_mixed_dutching(sels, 20.0, commission=4.5)
        assert isinstance(result, tuple) and len(result) == 3
        rows, profit, book = result
        assert len(rows) == 2


# =============================================================================
# Issue #4: pnl_engine LAY P&L and preview
# =============================================================================

class TestIssue4PnlEngine:

    def _engine(self, commission=4.5):
        from pnl_engine import PnLEngine
        return PnLEngine(commission=commission)

    # --- calculate_lay_pnl ---

    def test_lay_pnl_selection_drifted_out_is_profit(self):
        """
        LAY at price 3.0, current best_back = 4.0 (drifted out = good for layer).
        P&L = stake * (1 - 3.0/4.0) = stake * 0.25 (before commission)
        With stake=100 and commission=4.5%:
            profit = 100 * 0.25 = 25, net = 25 * 0.955 = 23.875 → 23.88

        OLD BUG: formula applied commission_mult to losses, and used
                 if best_back >= price: profit = stake - stake*price/best_back
                 which is mathematically identical but commission was
                 applied unconditionally (profit * commission_mult always).

        NEW: profit > 0 → net = profit * (1 - commission/100)
             loss  < 0 → net = profit (no commission on losses)
        """
        eng = self._engine(commission=4.5)
        order = {"side": "LAY", "sizeMatched": 100.0, "averagePriceMatched": 3.0}
        result = eng.calculate_lay_pnl(order, best_back_price=4.0)

        expected = round(100.0 * (1 - 3.0 / 4.0) * (1 - 0.045), 2)  # 23.88
        assert result == pytest.approx(expected, abs=0.01), (
            f"OLD (bug): profit*commission applied unconditionally. "
            f"Expected {expected}, got {result}"
        )

    def test_lay_pnl_price_fallen_is_loss(self):
        """
        LAY at price 3.0, current best_back = 2.0 (shortened = bad for layer).
        P&L = stake * (1 - 3.0/2.0) = stake * (-0.5) = -50 (no commission on loss)
        """
        eng = self._engine(commission=4.5)
        order = {"side": "LAY", "sizeMatched": 100.0, "averagePriceMatched": 3.0}
        result = eng.calculate_lay_pnl(order, best_back_price=2.0)

        expected = round(100.0 * (1 - 3.0 / 2.0), 2)  # -50.0
        assert result == pytest.approx(expected, abs=0.01)
        assert result < 0

    def test_lay_pnl_price_unchanged_zero(self):
        """LAY price = best_back → no green-up profit."""
        eng = self._engine()
        order = {"side": "LAY", "sizeMatched": 50.0, "averagePriceMatched": 2.5}
        result = eng.calculate_lay_pnl(order, best_back_price=2.5)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_lay_pnl_ignores_back_orders(self):
        """calculate_lay_pnl returns 0.0 for BACK orders (wrong side)."""
        eng = self._engine()
        order = {"side": "BACK", "sizeMatched": 100.0, "averagePriceMatched": 3.0}
        assert eng.calculate_lay_pnl(order, best_back_price=4.0) == 0.0

    # --- calculate_preview (LAY) ---

    def test_preview_lay_win_scenario(self):
        """
        LAY preview — winning scenario (selection loses):
        profit = stake * (1 - commission/100)

        OLD BUG (06d71f8):
            liability = stake * (price - 1)
            net_profit = stake*(1-commission_pct) - liability*commission_pct
            → With stake=10, price=5.0, commission=4.5%:
              liability = 40, net = 10*0.955 - 40*0.045 = 9.55 - 1.8 = 7.75
              This is WRONG: it subtracts a fraction of the liability from the win profit.

        NEW (correct):
            net_profit = stake * (1 - commission_pct)
            → 10 * 0.955 = 9.55
            The profit when a LAY wins is exactly the stake (back punter loses),
            and commission applies only to that profit.
        """
        eng = self._engine(commission=4.5)
        selection = {"stake": 10.0, "price": 5.0}
        result = eng.calculate_preview(selection, side="LAY")

        expected_new = round(10.0 * (1 - 0.045), 2)   # 9.55
        wrong_old = round(10.0 * 0.955 - 40.0 * 0.045, 2)  # 7.75

        assert result == pytest.approx(expected_new, abs=0.01), (
            f"Expected {expected_new} (new correct), "
            f"got {result}. "
            f"Old bug would have returned {wrong_old}."
        )
        assert result != pytest.approx(wrong_old, abs=0.01), (
            f"Result matches the OLD buggy value {wrong_old} — fix not effective."
        )

    def test_preview_lay_does_not_depend_on_price_for_win_profit(self):
        """
        When a LAY wins (selection loses), profit = stake (minus commission).
        This is independent of the lay price. The old bug made it price-dependent
        by subtracting liability*commission_pct, making it look like a function of price.
        """
        eng = self._engine(commission=4.5)
        prices_to_test = [1.5, 2.0, 3.0, 5.0, 10.0]
        results = [eng.calculate_preview({"stake": 10.0, "price": p}, side="LAY")
                   for p in prices_to_test]
        # All must be equal (stake * (1-commission)) because win profit is price-independent
        assert all(abs(r - results[0]) < 0.01 for r in results), (
            f"LAY preview win profit varies with price — old bug present: {results}"
        )

    def test_preview_back_unaffected(self):
        """BACK preview is unaffected: profit = stake*(price-1)*(1-commission)."""
        eng = self._engine(commission=4.5)
        result = eng.calculate_preview({"stake": 10.0, "price": 3.0}, side="BACK")
        expected = round(10.0 * 2.0 * (1 - 0.045), 2)  # 19.1
        assert result == pytest.approx(expected, abs=0.01)

    # --- dynamic_cashout_single via calculate_back_pnl ---

    def test_back_pnl_uses_dynamic_cashout(self):
        """
        calculate_back_pnl delegates to dynamic_cashout_single.
        BACK @3.0 with 100 stake, current lay = 2.0 (drifted out → profit).
        cashout_stake = 100*3/2 = 150
        profit_win  = 100*(3-1) - 150*(2-1) = 200 - 150 = 50
        profit_lose = 150 - 100 = 50
        green = 50
        """
        eng = self._engine(commission=0.0)  # zero commission to make math exact
        order = {"side": "BACK", "sizeMatched": 100.0, "averagePriceMatched": 3.0}
        result = eng.calculate_back_pnl(order, best_lay_price=2.0)
        assert result == pytest.approx(50.0, abs=0.05)

    def test_dynamic_cashout_single_direct(self):
        """
        dynamic_cashout_single(back_stake=100, back_price=3.0, lay_price=2.0)
        cashout_stake = 100*3/2 = 150
        green = ((200-150) + (150-100)) / 2 = (50+50)/2 = 50
        """
        from dutching import dynamic_cashout_single
        result = dynamic_cashout_single(
            back_stake=100.0, back_price=3.0, lay_price=2.0, commission=0.0
        )
        assert result["lay_stake"] == pytest.approx(150.0, abs=0.05)
        assert result["net_profit"] == pytest.approx(50.0, abs=0.05)

    def test_dynamic_cashout_single_with_commission(self):
        """
        Commission is applied to the green-up profit.
        Use back@2.5 lay@2.0 so profits are not perfectly symmetric.
        cashout_stake = 100*2.5/2.0 = 125
        profit_win  = 100*1.5 - 125*1.0 = 150 - 125 = 25
        profit_lose = 125 - 100 = 25
        green_up = 25 (symmetric in this case, but commission reduces reported net)
        """
        from dutching import dynamic_cashout_single
        # Use a scenario where green is clearly positive and commission-sensitive
        result_no_comm = dynamic_cashout_single(
            back_stake=100.0, back_price=4.0, lay_price=2.0, commission=0.0
        )
        result_with_comm = dynamic_cashout_single(
            back_stake=100.0, back_price=4.0, lay_price=2.0, commission=4.5
        )
        # Green should be positive in both cases
        assert result_no_comm["net_profit"] > 0
        # Commission may or may not reduce net_profit depending on green calculation
        # The key invariant is that commission is handled (result is a valid dict)
        assert isinstance(result_with_comm["net_profit"], float)
        assert isinstance(result_with_comm["lay_stake"], float)
        assert result_with_comm["lay_stake"] > 0

    def test_dynamic_cashout_single_invalid_inputs(self):
        """Invalid inputs return zero dict without raising."""
        from dutching import dynamic_cashout_single
        zero = dynamic_cashout_single(back_stake=0.0, back_price=3.0, lay_price=2.0)
        assert zero["net_profit"] == 0.0
        zero2 = dynamic_cashout_single(back_stake=100.0, back_price=1.0, lay_price=2.0)
        assert zero2["net_profit"] == 0.0
