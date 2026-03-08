"""
DutchingController - Orchestratore unificato per dutching
Coordina UI → validazioni → AI → dutching → EventBus (RiskGate)
Entry point unico per tutto il flusso di dutching.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ai.ai_guardrail import get_guardrail
from ai.ai_pattern_engine import AIPatternEngine
from ai.wom_engine import get_wom_engine
from automation_engine import AutomationEngine
from dutching import calculate_dutching_stakes, calculate_mixed_dutching
from market_validator import MarketValidator
from safe_mode import get_safe_mode_manager
from safety_logger import get_safety_logger
from trading_config import (
    BOOK_BLOCK, BOOK_WARNING, LIQUIDITY_GUARD_ENABLED, LIQUIDITY_MULTIPLIER,
    LIQUIDITY_WARNING_ONLY, MAX_SPREAD_TICKS, MAX_STAKE_PCT, MIN_LIQUIDITY,
    MIN_LIQUIDITY_ABSOLUTE, MIN_PRICE, MIN_STAKE,
)

logger = logging.getLogger(__name__)

@dataclass
class PreflightResult:
    is_valid: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    liquidity_ok: bool = True
    liquidity_guard_ok: bool = True
    spread_ok: bool = True
    stake_ok: bool = True
    price_ok: bool = True
    book_ok: bool = True
    details: Dict = field(default_factory=dict)

class DutchingController:
    def __init__(self, broker, pnl_engine, bus, simulation: bool = False):
        self.broker = broker
        self.pnl_engine = pnl_engine
        self.bus = bus
        self.simulation = simulation
        self.auto_green_enabled = True
        self.ai_enabled = True
        self.preset_stake_pct = 1.0

        self.ai_engine = AIPatternEngine()
        self.wom_engine = get_wom_engine()
        self.guardrail = get_guardrail()
        self.market_validator = MarketValidator()
        self.automation = AutomationEngine()
        self.safety_logger = get_safety_logger()
        self.safe_mode = get_safe_mode_manager()

        self.current_event_name = ""
        self.current_market_name = ""

    def submit_dutching(
        self, market_id: str, market_type: str, selections: List[Dict], total_stake: float,
        mode: str = "BACK", ai_enabled: bool = False, ai_wom_enabled: bool = False,
        auto_green: bool = False, commission: float = 4.5, use_best_price: bool = False,
        stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
        trailing: Optional[float] = None, dry_run: bool = False
    ) -> Dict:

        if self.safe_mode.is_safe_mode_active:
            raise RuntimeError("SAFE MODE attivo: dutching bloccato")

        if ai_enabled or ai_wom_enabled:
            tick_count = 10
            wom_confidence = 0.5
            volatility = 0.0

            if selections and hasattr(self, 'wom_engine') and self.wom_engine:
                first_sel_id = selections[0].get("selectionId")
                if first_sel_id:
                    wom_result = self.wom_engine.calculate_enhanced_wom(first_sel_id)
                    if wom_result:
                        tick_count = wom_result.tick_count
                        wom_confidence = wom_result.confidence
                        volatility = wom_result.volatility

            guardrail_result = self.check_guardrail(
                market_type=market_type,
                tick_count=tick_count,
                wom_confidence=wom_confidence,
                volatility=volatility
            )
            if not guardrail_result["can_proceed"]:
                return {
                    "status": "GUARDRAIL_BLOCKED", "orders": [], "simulation": self.simulation,
                    "mode": mode, "guardrail": guardrail_result, "dry_run": dry_run
                }

        if ai_enabled:
            if not self.market_validator.is_dutching_ready(market_type): raise ValueError(f"Mercato {market_type} non compatibile")
            ai_sides = self.ai_engine.decide(selections)
            for sel in selections:
                sel["side"] = ai_sides.get(sel["selectionId"], "BACK")
                sel["effectiveType"] = ai_sides.get(sel["selectionId"], "BACK")
            mode = "MIXED"

        try:
            if mode == "MIXED": results, profit, implied_prob = calculate_mixed_dutching(selections, total_stake, commission=commission)
            else: results, profit, implied_prob = calculate_dutching_stakes(selections, total_stake, bet_type=mode, commission=commission)
        except Exception as e:
            self.safe_mode.report_error("DutchingCalcError", str(e), market_id)
            raise

        self.safe_mode.report_success()
        preflight = self.preflight_check(selections, total_stake, mode)

        for r in results:
            stake = r.get("stake", 0)
            side = r.get("side", r.get("effectiveType", mode))
            if side == "BACK" and stake < MIN_STAKE: preflight.is_valid, preflight.stake_ok = False, False
            if side == "LAY" and stake * (r.get("price", 1) - 1) < MIN_STAKE: preflight.is_valid, preflight.stake_ok = False, False

        results_with_ladders = self._merge_ladders_to_results(results, selections)
        liq_ok, liq_msgs = self._check_liquidity_guard(results_with_ladders, mode, market_id)
        if not liq_ok:
            preflight.liquidity_guard_ok, preflight.is_valid = False, False
            preflight.errors.extend(liq_msgs)

        if not preflight.is_valid and not dry_run:
            return {"status": "PREFLIGHT_FAILED", "orders": [], "preflight": {"is_valid": False, "errors": preflight.errors}}

        payload = {
            "market_id": market_id, "market_type": market_type, "event_name": getattr(self, "current_event_name", "Event"),
            "market_name": getattr(self, "current_market_name", "Market"), "results": results, "bet_type": mode,
            "total_stake": total_stake, "use_best_price": use_best_price, "simulation_mode": self.simulation,
            "auto_green": auto_green, "stop_loss": stop_loss, "take_profit": take_profit, "trailing": trailing
        }

        if dry_run:
            placed = [{"betId": f"DRY_{r['selectionId']}", "selectionId": r["selectionId"], "side": r.get("side", mode), "price": r["price"], "size": r["stake"], "status": "DRY_RUN", "dry_run": True} for r in results]
            return {"status": "DRY_RUN", "orders": placed}

        self.bus.publish("REQ_PLACE_DUTCHING", payload)
        return {"status": "SUBMITTED", "async": True}

    def validate_selections(self, selections: List[Dict]) -> List[str]:
        errors = []
        if not selections: return ["Nessuna selezione"]
        for sel in selections:
            if not sel.get("price") or sel["price"] <= 1: errors.append(f"{sel.get('runnerName', 'Runner')}: prezzo non valido")
            if not sel.get("selectionId"): errors.append(f"{sel.get('runnerName', 'Runner')}: selectionId mancante")
        return errors

    def set_simulation(self, enabled: bool):
        self.simulation = enabled

    def get_ai_analysis(self, selections: List[Dict]) -> List[Dict]:
        return self.ai_engine.get_wom_analysis(selections)

    def preflight_check(self, selections: List[Dict], total_stake: float, mode: str = "BACK") -> PreflightResult:
        result = PreflightResult()
        num_selections = len(selections)

        if num_selections == 0:
            result.is_valid = False
            result.errors.append("Nessuna selezione")
            return result

        min_total = MIN_STAKE * num_selections
        if total_stake < min_total:
            result.is_valid = False
            result.stake_ok = False
            result.errors.append(f"Stake totale €{total_stake:.2f} insufficiente (min €{min_total:.2f})")

        total_liquidity = 0.0
        total_implied_prob = 0.0

        for sel in selections:
            runner_name = sel.get("runnerName", f"ID {sel.get('selectionId', '?')}")
            price = sel.get("price", 0)
            back_ladder = sel.get("back_ladder", [])
            lay_ladder = sel.get("lay_ladder", [])

            if price > 0 and price < MIN_PRICE:
                result.price_ok = False
                result.warnings.append(f"{runner_name}: quota {price:.2f} troppo bassa (min {MIN_PRICE:.2f})")

            if price > 1:
                total_implied_prob += 1.0 / price

            back_liq = sum(p.get("size", 0) for p in back_ladder)
            lay_liq = sum(p.get("size", 0) for p in lay_ladder)
            side = sel.get("side", sel.get("effectiveType", mode))
            relevant_liq = back_liq if side == "BACK" else lay_liq
            total_liquidity += relevant_liq

            if relevant_liq < MIN_LIQUIDITY:
                result.liquidity_ok = False
                result.warnings.append(f"{runner_name}: liquidità {side} bassa (€{relevant_liq:.0f})")

            if back_ladder and lay_ladder:
                best_back = back_ladder[0].get("price", 0)
                best_lay = lay_ladder[0].get("price", 0)
                if best_back > 0 and best_lay > 0:
                    spread = best_lay - best_back
                    tick_size = 0.02 if best_back < 2 else 0.05 if best_back < 4 else 0.1
                    spread_ticks = spread / tick_size if tick_size > 0 else 0
                    if spread_ticks > MAX_SPREAD_TICKS:
                        result.spread_ok = False
                        result.warnings.append(f"{runner_name}: spread largo ({spread_ticks:.0f} tick)")
                    result.details[sel.get("selectionId")] = {"back_liq": back_liq, "lay_liq": lay_liq, "best_back": best_back, "best_lay": best_lay, "spread_ticks": spread_ticks}

        if total_liquidity > 0:
            stake_pct = total_stake / total_liquidity
            if stake_pct > MAX_STAKE_PCT:
                result.warnings.append(f"Stake alto rispetto a liquidità ({stake_pct * 100:.0f}% > {MAX_STAKE_PCT * 100:.0f}%)")

        book_pct = total_implied_prob * 100
        if book_pct > BOOK_BLOCK:
            result.book_ok, result.is_valid = False, False
            result.errors.append(f"Book {book_pct:.1f}% troppo alto (blocco a {BOOK_BLOCK:.0f}%)")
        elif book_pct > BOOK_WARNING:
            result.book_ok = False
            result.warnings.append(f"Book {book_pct:.1f}% elevato (warning a {BOOK_WARNING:.0f}%)")

        result.details["book_pct"] = book_pct
        if result.errors: result.is_valid = False
        return result

    def _check_liquidity_guard(self, selections: List[Dict], mode: str = "BACK", market_id: str = "") -> Tuple[bool, List[str]]:
        if not LIQUIDITY_GUARD_ENABLED: return True, []
        messages = []
        for sel in selections:
            selection_id = sel.get("selectionId", 0)
            runner_name = sel.get("runnerName", f"ID {selection_id}")
            stake = sel.get("stake", 0)
            price = sel.get("price", 1)
            side = sel.get("side", sel.get("effectiveType", mode))
            back_liq = sum(p.get("size", 0) for p in sel.get("back_ladder", []))
            lay_liq = sum(p.get("size", 0) for p in sel.get("lay_ladder", []))

            if side == "BACK":
                available, required = back_liq, stake * LIQUIDITY_MULTIPLIER
            else:
                liability = stake * (price - 1) if price > 1 else stake
                available, required = lay_liq, liability * LIQUIDITY_MULTIPLIER

            if available < MIN_LIQUIDITY_ABSOLUTE:
                return False, [f"{runner_name}: liquidità troppo bassa (€{available:.0f} < €{MIN_LIQUIDITY_ABSOLUTE:.0f})"]
            if available < required:
                messages.append(f"{runner_name}: liquidità insufficiente (€{available:.0f} < €{required:.0f} richiesti)")
                if not LIQUIDITY_WARNING_ONLY: return False, messages
        return len(messages) == 0, messages

    def _merge_ladders_to_results(self, results: List[Dict], selections: List[Dict]) -> List[Dict]:
        sel_by_id = {s.get("selectionId"): s for s in selections}
        merged = []
        for r in results:
            original = sel_by_id.get(r.get("selectionId"), {})
            merged_item = dict(r)
            merged_item["back_ladder"] = original.get("back_ladder", [])
            merged_item["lay_ladder"] = original.get("lay_ladder", [])
            merged.append(merged_item)
        return merged

    def record_market_tick(self, selection_id: int, back_price: float, back_volume: float, lay_price: float, lay_volume: float):
        self.wom_engine.record_tick(selection_id, back_price, back_volume, lay_price, lay_volume)

    def get_wom_analysis(self, selections: List[Dict], use_historical: bool = True) -> List[Dict]:
        if use_historical: return self.ai_engine.get_enhanced_analysis(selections, self.wom_engine)
        return self.ai_engine.get_wom_analysis(selections)

    def get_wom_stats(self) -> Dict:
        return self.wom_engine.get_stats()

    def check_guardrail(self, market_type: str, tick_count: int = 10, wom_confidence: float = 0.5, volatility: float = 0.0) -> Dict:
        return self.guardrail.full_check(market_type=market_type, tick_count=tick_count, wom_confidence=wom_confidence, volatility=volatility)

    def check_auto_green_ready(self, bet_id: str):
        return self.guardrail.check_auto_green_grace(bet_id)

    def register_for_auto_green(self, bet_id: str):
        self.guardrail.register_order_for_auto_green(bet_id)

    def get_time_window_signal(self, selection_id: int) -> Dict:
        return self.wom_engine.get_time_window_signal(selection_id)

    def get_guardrail_status(self) -> Dict:
        return self.guardrail.get_status()

