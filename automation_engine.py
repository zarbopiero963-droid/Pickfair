"""
Automation Engine (Hedge-Fund Grade)
Gestisce l'automazione, gli stop loss e previene double-triggers.
"""

import logging
import threading
import time
from typing import Any, Dict

logger = logging.getLogger("AUTO_ENGINE")


class AutomationEngine:
    def __init__(self, controller=None):
        self.controller = controller
        self._action_locks = {}
        self._last_action_time = {}
        self._cooldown_ms = 1500
        self._global_lock = threading.Lock()
        self.running = False

    def start(self):
        """Compatibilità legacy."""
        self.running = True

    def stop(self):
        """Compatibilità legacy."""
        self.running = False

    def _is_on_cooldown(self, market_id: str) -> bool:
        """Verifica se il mercato è in cooldown per evitare double triggers."""
        market_id = str(market_id or "").strip()
        if not market_id:
            return False

        with self._global_lock:
            now = time.time() * 1000
            last_time = self._last_action_time.get(market_id, 0)
            if now - last_time < self._cooldown_ms:
                return True
            self._last_action_time[market_id] = now
            return False

    def _get_orders(self):
        if not self.controller:
            return []

        try:
            if getattr(self.controller, "simulation", False):
                broker = getattr(self.controller, "broker", None)
                if broker and hasattr(broker, "get_open_positions"):
                    return broker.get_open_positions() or []
                return []

            client = getattr(self.controller, "client", None)
            if client and hasattr(client, "get_current_orders"):
                orders = client.get_current_orders() or []
                if isinstance(orders, dict):
                    current = orders.get("currentOrders")
                    if current is not None:
                        return current or []
                    matched = orders.get("matched", []) or []
                    unmatched = orders.get("unmatched", []) or []
                    return matched + unmatched
                return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.error(f"[AUTO] Errore recupero ordini: {e}")

        return []

    def process_tick(self, market_id: str, market_data: Dict[str, Any]):
        """Analizza il tick e decide se agire, protetto da cooldown."""
        market_id = str(market_id or "").strip()
        if not market_id:
            return

        if self._is_on_cooldown(market_id):
            return

        orders = self._get_orders()
        if not orders:
            return

        market_orders = [o for o in orders if str(o.get("marketId", "")) == market_id]
        if not market_orders:
            return

        for order in market_orders:
            self._evaluate_order(order, market_data or {})

    def _evaluate_order(self, order: Dict, market_data: Dict):
        """Valuta le condizioni di uscita per un singolo ordine."""
        try:
            market_status = str(market_data.get("status", "OPEN")).upper()

            if should_auto_green(order, market_status):
                controller = self.controller
                if controller and hasattr(controller, "execute_auto_green"):
                    controller.execute_auto_green(order, market_data)
        except Exception as e:
            logger.error(f"[AUTO] Errore valutazione ordine: {e}")


def _order_get(order: Any, key: str, default=None):
    if isinstance(order, dict):
        return order.get(key, default)

    meta = getattr(order, "meta", None)
    if isinstance(meta, dict) and key in meta:
        return meta.get(key, default)

    return getattr(order, key, default)


def should_auto_green(order: Any, market_status: str) -> bool:
    """Verifica se l'ordine ha i requisiti per l'auto-green."""
    status = str(market_status or "").upper()
    if status in ["SUSPENDED", "CLOSED"]:
        return False

    auto_green = _order_get(order, "auto_green_enabled", None)
    if auto_green is None:
        auto_green = _order_get(order, "auto_green", False)

    if not bool(auto_green):
        return False

    is_simulation = bool(_order_get(order, "simulation", False))
    required_delay = 0.0 if is_simulation else 2.0

    placed_at = float(_order_get(order, "placed_at", 0) or 0)
    if placed_at <= 0:
        return False

    if time.time() - placed_at < required_delay:
        return False

    return True


def get_auto_green_remaining_delay(order: Any) -> float:
    placed_at = float(_order_get(order, "placed_at", 0) or 0)
    if placed_at <= 0:
        return 0.0

    is_simulation = bool(_order_get(order, "simulation", False))
    required_delay = 0.0 if is_simulation else 2.0

    elapsed = time.time() - placed_at
    return max(0.0, required_delay - elapsed)
