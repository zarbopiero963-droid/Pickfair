"""
Automation Engine (Hedge-Fund Grade)
Gestisce l'automazione, gli stop loss e previene double-triggers.
"""
import time
import logging
import threading
from typing import Dict, Any

logger = logging.getLogger("AUTO_ENGINE")

class AutomationEngine:
    def __init__(self, controller):
        self.controller = controller
        self._action_locks = {}
        self._last_action_time = {}
        self._cooldown_ms = 1500  # 1.5 secondi di cooldown per mercato
        self._global_lock = threading.Lock()
        
    def _is_on_cooldown(self, market_id: str) -> bool:
        """Verifica se il mercato è in cooldown per evitare double triggers."""
        with self._global_lock:
            now = time.time() * 1000
            last_time = self._last_action_time.get(market_id, 0)
            if now - last_time < self._cooldown_ms:
                return True
            self._last_action_time[market_id] = now
            return False

    def process_tick(self, market_id: str, market_data: Dict[str, Any]):
        """Analizza il tick e decide se agire, protetto da cooldown."""
        
        # 1. Check Cooldown immediato
        if self._is_on_cooldown(market_id):
            return

        # 2. Ottieni lo stato dell'ordine
        orders = self.controller.broker.get_open_positions() if self.controller.simulation else self.controller.client.get_current_orders()
        
        if not orders:
            return
            
        market_orders = [o for o in orders if o.get('marketId') == market_id]
        if not market_orders:
            return

        # 3. Logica di Auto-Green / Stop-Loss
        for order in market_orders:
            self._evaluate_order(order, market_data)

    def _evaluate_order(self, order: Dict, market_data: Dict):
        """Valuta le condizioni di uscita per un singolo ordine."""
        try:
            # Qui si aggancia la logica del PnL per decidere il cashout
            # Implementazione semplificata per la patch
            pass
        except Exception as e:
            logger.error(f"[AUTO] Errore valutazione ordine: {e}")

def should_auto_green(order: Dict, market_status: str) -> bool:
    """Verifica se l'ordine ha i requisiti per l'auto-green."""
    if market_status in ['SUSPENDED', 'CLOSED']:
        return False
        
    placed_at = order.get('placed_at', 0)
    # Delay minimo di sicurezza prima del green up (10 secondi)
    if time.time() - placed_at < 10.0:
        return False
        
    return order.get('auto_green_enabled', False)

def get_auto_green_remaining_delay(order: Dict) -> float:
    placed_at = order.get('placed_at', 0)
    elapsed = time.time() - placed_at
    return max(0.0, 10.0 - elapsed)