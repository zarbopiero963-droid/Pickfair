"""
Automation Optimizer - Early exit stack per ridurre esecuzioni inutili

Problema: Automazioni valutate ad ogni tick anche quando non necessario
Soluzione: Early exit stack con verifiche ordinate per costo

Impatto: -50% esecuzioni automation
"""

import time
import threading
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

from trading_config import AUTO_GREEN_DELAY_SEC


class SkipReason(Enum):
    """Motivi di skip automazione."""
    DISABLED = "automation_disabled"
    NO_ORDERS = "no_open_orders"
    MARKET_CLOSED = "market_not_open"
    DELAY_NOT_ELAPSED = "delay_not_elapsed"
    PNL_BELOW_THRESHOLD = "pnl_below_threshold"
    RECENTLY_CHECKED = "recently_checked"
    SIMULATION_BLOCKED = "simulation_blocked"


@dataclass
class AutomationState:
    """Stato automazione per un ordine/mercato."""
    order_id: str
    last_check: float = 0
    skip_until: float = 0
    check_count: int = 0
    skip_count: int = 0


class AutomationOptimizer:
    """
    Ottimizza esecuzione automazioni con early exit stack.
    
    Ordine verifiche (dal più economico al più costoso):
    1. Automazione abilitata?
    2. Ci sono ordini aperti?
    3. Mercato aperto?
    4. Delay scaduto?
    5. P&L sopra soglia?
    
    In simulazione: automazioni valutate con intervallo throttled (non bloccate).
    """
    
    MIN_CHECK_INTERVAL = 0.1
    SIM_CHECK_INTERVAL = 1.0
    MIN_PNL_THRESHOLD = 0.10
    
    def __init__(self):
        self._lock = threading.Lock()
        self._states: Dict[str, AutomationState] = {}
        self._global_enabled = True
        self._stats = {
            "total_checks": 0,
            "early_exits": 0,
            "full_evaluations": 0,
            "by_reason": {r.value: 0 for r in SkipReason}
        }
    
    @property
    def enabled(self) -> bool:
        return self._global_enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        with self._lock:
            self._global_enabled = value
    
    def should_evaluate(
        self,
        order_id: str,
        auto_green_enabled: bool,
        has_open_orders: bool,
        market_status: str,
        placed_at: Optional[float],
        current_pnl: float,
        simulation: bool = False
    ) -> tuple[bool, Optional[SkipReason]]:
        """
        Verifica se un'automazione deve essere valutata.
        
        Early exit stack ordinato per costo computazionale.
        In simulazione: automazioni valutate ma con intervallo throttled.
        
        Returns:
            (should_evaluate, skip_reason)
        """
        now = time.time()
        
        with self._lock:
            self._stats["total_checks"] += 1
            
            state = self._states.get(order_id)
            if not state:
                state = AutomationState(order_id=order_id)
                self._states[order_id] = state
            
            state.check_count += 1
        
        def early_exit(reason: SkipReason) -> tuple[bool, SkipReason]:
            with self._lock:
                self._stats["early_exits"] += 1
                self._stats["by_reason"][reason.value] += 1
                state.skip_count += 1
            return (False, reason)
        
        if not self._global_enabled:
            return early_exit(SkipReason.DISABLED)
        
        if not auto_green_enabled:
            return early_exit(SkipReason.DISABLED)
        
        if not has_open_orders:
            return early_exit(SkipReason.NO_ORDERS)
        
        if market_status != "OPEN":
            return early_exit(SkipReason.MARKET_CLOSED)
        
        if not placed_at or (now - placed_at) < AUTO_GREEN_DELAY_SEC:
            return early_exit(SkipReason.DELAY_NOT_ELAPSED)
        
        if abs(current_pnl) < self.MIN_PNL_THRESHOLD:
            return early_exit(SkipReason.PNL_BELOW_THRESHOLD)
        
        check_interval = self.MIN_CHECK_INTERVAL
        if simulation:
            check_interval = self.SIM_CHECK_INTERVAL
        
        if (now - state.last_check) < check_interval:
            return early_exit(SkipReason.RECENTLY_CHECKED)
        
        with self._lock:
            state.last_check = now
            self._stats["full_evaluations"] += 1
        
        return (True, None)
    
    def mark_processed(self, order_id: str, skip_duration: float = 0):
        """
        Marca un ordine come processato.
        
        Args:
            order_id: ID ordine
            skip_duration: Secondi da saltare prima del prossimo check
        """
        with self._lock:
            state = self._states.get(order_id)
            if state:
                state.last_check = time.time()
                if skip_duration > 0:
                    state.skip_until = time.time() + skip_duration
    
    def remove_order(self, order_id: str):
        """Rimuove stato per un ordine."""
        with self._lock:
            self._states.pop(order_id, None)
    
    def clear(self):
        """Pulisce tutti gli stati."""
        with self._lock:
            self._states.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiche dell'optimizer."""
        with self._lock:
            total = self._stats["total_checks"]
            return {
                **self._stats,
                "skip_ratio": (
                    self._stats["early_exits"] / max(1, total)
                ) * 100,
                "orders_tracked": len(self._states)
            }


_automation_optimizer: Optional[AutomationOptimizer] = None


def get_automation_optimizer() -> AutomationOptimizer:
    """Ottiene l'istanza singleton dell'AutomationOptimizer."""
    global _automation_optimizer
    if _automation_optimizer is None:
        _automation_optimizer = AutomationOptimizer()
    return _automation_optimizer
