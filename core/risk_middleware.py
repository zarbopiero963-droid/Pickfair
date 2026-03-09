"""
Risk Middleware - Modalità OMS Puro (Modalità A)
Agisce come Gatekeeper tecnico prima del Trading Engine.
Funzioni:
1. Anti-Duplicate (Circuit Breaker contro spam di click/segnali)
2. Normalizzazione/Shaping del Payload
3. Forwarding (REQ_* -> CMD_*)
NON decide la validità strategica della scommessa (niente Guardrail/Volatilità).
"""

import logging
import time
import hashlib
import json

logger = logging.getLogger("RiskMiddleware")


class RiskMiddleware:
    def __init__(self, event_bus, guardrail=None, wom_engine=None):
        self.bus = event_bus

        # In Modalità A (OMS Puro), non usiamo attivamente l'AI per bloccare.
        # Li teniamo nell'init solo per non rompere la signature di chiamata in main.py
        self.guardrail = guardrail
        self.wom_engine = wom_engine

        # Stato anti-spam
        self.recent_requests = {}
        self.DUPLICATE_WINDOW = 2.0  # Secondi di cooldown per ordini identici

        # Sottoscrizioni agli Intenti (REQ)
        self.bus.subscribe("REQ_QUICK_BET", self._handle_quick_bet)
        self.bus.subscribe("REQ_PLACE_DUTCHING", self._handle_dutching)
        self.bus.subscribe("REQ_EXECUTE_CASHOUT", self._handle_cashout)

    def _is_duplicate(self, payload):
        """Genera un hash della richiesta per bloccare doppi-click accidentali."""
        try:
            # Crea un dizionario sicuro per il json.dumps
            safe_payload = {k: v for k, v in payload.items() if isinstance(v, (str, int, float, bool, list, dict))}
            payload_str = json.dumps(safe_payload, sort_keys=True)
            req_hash = hashlib.sha256(payload_str.encode()).hexdigest()

            now = time.time()
            if req_hash in self.recent_requests:
                if now - self.recent_requests[req_hash] < self.DUPLICATE_WINDOW:
                    return True

            self.recent_requests[req_hash] = now
            # Cleanup hash vecchi per non saturare la memoria
            self.recent_requests = {k: v for k, v in self.recent_requests.items() if now - v < 10.0}
            return False

        except Exception as e:
            logger.error(f"[RiskGate] Errore calcolo hash: {e}")
            return False # Se fallisce l'hash, facciamo passare per non bloccare il sistema

    def _handle_quick_bet(self, payload):
        if self._is_duplicate(payload):
            logger.warning("[RiskGate] REQ_QUICK_BET duplicata (Spam-Click). Ignorata.")
            return

        # Shaping & Normalizzazione (Ci assicuriamo che i tipi dato siano perfetti per l'OMS)
        normalized = {
            "market_id": str(payload.get("market_id", "")),
            "selection_id": payload.get("selection_id"),
            "bet_type": str(payload.get("bet_type", "BACK")).upper(),
            "price": float(payload.get("price", 0.0)),
            "stake": float(payload.get("stake", 0.0)),
            "market_type": str(payload.get("market_type", "MATCH_ODDS")),
            "event_name": str(payload.get("event_name", "")),
            "market_name": str(payload.get("market_name", "")),
            "runner_name": str(payload.get("runner_name", str(payload.get("selection_id")))),
            "simulation_mode": bool(payload.get("simulation_mode", False)),
            "source": str(payload.get("source", "UI"))
        }

        logger.info(f"[RiskGate] Forwarding REQ_QUICK_BET -> CMD_QUICK_BET")
        self.bus.publish("CMD_QUICK_BET", normalized)

    def _handle_dutching(self, payload):
        if self._is_duplicate(payload):
            logger.warning("[RiskGate] REQ_PLACE_DUTCHING duplicata (Spam-Click). Ignorata.")
            return

        # Shaping
        normalized = {
            "market_id": str(payload.get("market_id", "")),
            "market_type": str(payload.get("market_type", "MATCH_ODDS")),
            "event_name": str(payload.get("event_name", "")),
            "market_name": str(payload.get("market_name", "")),
            "results": payload.get("results", []), # Lista dei runner calcolati
            "bet_type": str(payload.get("bet_type", "BACK")).upper(),
            "total_stake": float(payload.get("total_stake", 0.0)),
            "use_best_price": bool(payload.get("use_best_price", False)),
            "simulation_mode": bool(payload.get("simulation_mode", False)),
            "source": str(payload.get("source", "UI"))
        }

        logger.info(f"[RiskGate] Forwarding REQ_PLACE_DUTCHING -> CMD_PLACE_DUTCHING")
        self.bus.publish("CMD_PLACE_DUTCHING", normalized)

    def _handle_cashout(self, payload):
        if self._is_duplicate(payload):
            logger.warning("[RiskGate] REQ_EXECUTE_CASHOUT duplicata (Spam-Click). Ignorata.")
            return

        # Il payload del cashout è costruito dal monitoring module, lo passiamo in modo trasparente
        logger.info(f"[RiskGate] Forwarding REQ_EXECUTE_CASHOUT -> CMD_EXECUTE_CASHOUT")
        self.bus.publish("CMD_EXECUTE_CASHOUT", payload)

