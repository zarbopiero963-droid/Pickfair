"""
Risk Middleware (RiskGate)
Architettura Tier-1: Separa l'OMS (TradingEngine) dalle logiche di rischio.
"""
import logging

logger = logging.getLogger(__name__)

class RiskMiddleware:
    def __init__(self, bus, guardrail, wom_engine):
        self.bus = bus
        self.guardrail = guardrail
        self.wom_engine = wom_engine

        self.bus.subscribe("REQ_QUICK_BET", self._evaluate_quick_bet)
        self.bus.subscribe("REQ_PLACE_DUTCHING", self._evaluate_dutching)
        self.bus.subscribe("REQ_EXECUTE_CASHOUT", self._evaluate_cashout)

    def _evaluate_quick_bet(self, payload):
        selection_id = payload.get('selection_id')

        live_volatility = 0.0
        if self.wom_engine and selection_id:
            live_volatility = self.wom_engine.calculate_volatility(selection_id)

        if hasattr(self.guardrail, 'check_volatility'):
            ok, reason = self.guardrail.check_volatility(live_volatility)
            if not ok:
                logger.warning(f"[RiskGate] Quick Bet bloccata: {reason}")
                self.bus.publish("QUICK_BET_FAILED", f"RISK GATE BLOCKED: {reason}")
                return
        self.bus.publish("CMD_QUICK_BET", payload)

    def _evaluate_dutching(self, payload):
        live_volatility = 0.0
        if self.wom_engine:
            results = payload.get('results', [])
            if results:
                first_sel = results[0].get('selectionId')
                if first_sel:
                    live_volatility = self.wom_engine.calculate_volatility(first_sel)

        safety_check = self.guardrail.full_check(
            market_type=payload.get('market_type', 'MATCH_ODDS'),
            tick_count=10,
            wom_confidence=0.5,
            volatility=live_volatility
        )

        if not safety_check['can_proceed']:
            reasons = " | ".join(safety_check['reasons'])
            logger.warning(f"[RiskGate] Dutching bloccato: {reasons}")
            self.bus.publish("DUTCHING_FAILED", f"RISK GATE BLOCKED: {reasons}")
            return
        self.bus.publish("CMD_PLACE_DUTCHING", payload)

    def _evaluate_cashout(self, payload):
        logger.info("[RiskGate] Cashout request approvata automaticamente.")
        self.bus.publish("CMD_EXECUTE_CASHOUT", payload)

