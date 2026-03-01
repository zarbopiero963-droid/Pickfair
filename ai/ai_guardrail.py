"""
AI Guardrail - Protezione automatica per trading AI

v3.67 - Sistema di protezione multi-livello:
1. Blocco mercati non-ready per dutching
2. Delay anti-overtrade per auto-green
3. Limite frequenza ordini
4. Protezione volatilità
5. Circuit breaker su errori consecutivi

Integrazione con DutchingController e SafeMode.
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class GuardrailLevel(Enum):
    """Livelli di protezione."""
    NORMAL = "normal"
    WARNING = "warning"
    BLOCKED = "blocked"


class BlockReason(Enum):
    """Motivi di blocco."""
    MARKET_NOT_READY = "market_not_ready"
    HIGH_VOLATILITY = "high_volatility"
    OVERTRADE_PROTECTION = "overtrade_protection"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    INSUFFICIENT_DATA = "insufficient_data"
    GRACE_PERIOD = "grace_period"
    MANUAL_BLOCK = "manual_block"


@dataclass
class GuardrailConfig:
    """Configurazione guardrail."""
    auto_green_grace_sec: float = 3.0
    min_tick_count: int = 10
    max_volatility: float = 0.8
    max_orders_per_minute: int = 10
    consecutive_error_limit: int = 3
    cooldown_after_error_sec: float = 30.0
    min_wom_confidence: float = 0.3
    dutching_ready_market_types: Set[str] = field(default_factory=lambda: {
        "MATCH_ODDS", "WINNER", "OVER_UNDER_25", "OVER_UNDER_35",
        "CORRECT_SCORE", "HALF_TIME", "BOTH_TEAMS_TO_SCORE"
    })


@dataclass
class OrderRecord:
    """Record di un ordine per tracking."""
    timestamp: float
    market_id: str
    selection_id: int
    side: str
    stake: float
    success: bool = True


@dataclass
class GuardrailState:
    """Stato corrente del guardrail."""
    level: GuardrailLevel = GuardrailLevel.NORMAL
    block_reasons: List[BlockReason] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    last_order_time: float = 0.0
    consecutive_errors: int = 0
    blocked_until: float = 0.0
    order_history: List[OrderRecord] = field(default_factory=list)


class AIGuardrail:
    """
    Sistema di protezione AI per trading.
    
    Verifica condizioni di sicurezza prima di ogni operazione:
    - Mercato compatibile con dutching
    - Dati WoM sufficienti
    - Non in periodo di grazia auto-green
    - Non supera limite ordini/minuto
    - Volatilità accettabile
    """
    
    def __init__(self, config: Optional[GuardrailConfig] = None):
        self.config = config or GuardrailConfig()
        self.state = GuardrailState()
        self._lock = threading.RLock()
        self._pending_auto_green: Dict[str, float] = {}
    
    def check_market_ready(self, market_type: str) -> tuple[bool, Optional[BlockReason]]:
        """
        Verifica se il mercato è compatibile con AI dutching.
        
        Args:
            market_type: Tipo mercato (MATCH_ODDS, WINNER, etc.)
            
        Returns:
            (is_ready, block_reason)
        """
        if market_type in self.config.dutching_ready_market_types:
            return True, None
        return False, BlockReason.MARKET_NOT_READY
    
    def check_wom_data(self, tick_count: int, confidence: float) -> tuple[bool, Optional[BlockReason]]:
        """
        Verifica se ci sono dati WoM sufficienti.
        
        Args:
            tick_count: Numero tick disponibili
            confidence: Confidence WoM [0, 1]
            
        Returns:
            (is_ready, block_reason)
        """
        if tick_count < self.config.min_tick_count:
            return False, BlockReason.INSUFFICIENT_DATA
        if confidence < self.config.min_wom_confidence:
            return False, BlockReason.INSUFFICIENT_DATA
        return True, None
    
    def check_volatility(self, volatility: float) -> tuple[bool, Optional[BlockReason]]:
        """
        Verifica se la volatilità è accettabile.
        
        Args:
            volatility: Indice volatilità [0, 1]
            
        Returns:
            (is_ready, block_reason)
        """
        if volatility > self.config.max_volatility:
            return False, BlockReason.HIGH_VOLATILITY
        return True, None
    
    def check_auto_green_grace(self, bet_id: str) -> tuple[bool, float]:
        """
        Verifica se un ordine è ancora nel periodo di grazia auto-green.
        
        Args:
            bet_id: ID ordine
            
        Returns:
            (can_green, remaining_seconds)
        """
        with self._lock:
            if bet_id not in self._pending_auto_green:
                return True, 0.0
            
            placed_at = self._pending_auto_green[bet_id]
            elapsed = time.time() - placed_at
            remaining = self.config.auto_green_grace_sec - elapsed
            
            if remaining <= 0:
                del self._pending_auto_green[bet_id]
                return True, 0.0
            
            return False, remaining
    
    def register_order_for_auto_green(self, bet_id: str, placed_at: Optional[float] = None):
        """
        Registra un ordine per monitoraggio auto-green.
        
        Args:
            bet_id: ID ordine
            placed_at: Timestamp piazzamento (default: now)
        """
        with self._lock:
            self._pending_auto_green[bet_id] = placed_at or time.time()
    
    def check_order_rate(self) -> tuple[bool, Optional[BlockReason]]:
        """
        Verifica se il rate di ordini è accettabile.
        
        Returns:
            (can_order, block_reason)
        """
        with self._lock:
            now = time.time()
            one_minute_ago = now - 60.0
            
            recent_orders = [o for o in self.state.order_history 
                           if o.timestamp > one_minute_ago]
            
            if len(recent_orders) >= self.config.max_orders_per_minute:
                return False, BlockReason.OVERTRADE_PROTECTION
            
            return True, None
    
    def check_error_state(self) -> tuple[bool, Optional[BlockReason]]:
        """
        Verifica se siamo in cooldown per errori consecutivi.
        
        Returns:
            (can_proceed, block_reason)
        """
        with self._lock:
            if self.state.consecutive_errors >= self.config.consecutive_error_limit:
                if time.time() < self.state.blocked_until:
                    return False, BlockReason.CONSECUTIVE_ERRORS
                else:
                    self.state.consecutive_errors = 0
                    self.state.blocked_until = 0.0
            
            return True, None
    
    def record_order(self, market_id: str, selection_id: int, 
                     side: str, stake: float, success: bool = True):
        """
        Registra un ordine eseguito.
        
        Args:
            market_id: ID mercato
            selection_id: ID runner
            side: BACK o LAY
            stake: Stake piazzato
            success: Se l'ordine è andato a buon fine
        """
        with self._lock:
            record = OrderRecord(
                timestamp=time.time(),
                market_id=market_id,
                selection_id=selection_id,
                side=side,
                stake=stake,
                success=success
            )
            self.state.order_history.append(record)
            
            if len(self.state.order_history) > 100:
                self.state.order_history = self.state.order_history[-100:]
            
            if success:
                self.state.consecutive_errors = 0
            else:
                self.state.consecutive_errors += 1
                if self.state.consecutive_errors >= self.config.consecutive_error_limit:
                    self.state.blocked_until = time.time() + self.config.cooldown_after_error_sec
                    logger.warning(f"[GUARDRAIL] Consecutive errors: {self.state.consecutive_errors}, blocked for {self.config.cooldown_after_error_sec}s")
    
    def full_check(
        self,
        market_type: str,
        tick_count: int = 0,
        wom_confidence: float = 0.5,
        volatility: float = 0.0
    ) -> Dict:
        """
        Esegue tutti i controlli guardrail.
        
        Args:
            market_type: Tipo mercato
            tick_count: Numero tick disponibili
            wom_confidence: Confidence WoM
            volatility: Indice volatilità
            
        Returns:
            Dict con can_proceed, level, reasons, warnings
        """
        with self._lock:
            reasons = []
            warnings = []
            
            ok, reason = self.check_market_ready(market_type)
            if not ok:
                reasons.append(reason)
            
            ok, reason = self.check_wom_data(tick_count, wom_confidence)
            if not ok:
                reasons.append(reason)
            
            ok, reason = self.check_volatility(volatility)
            if not ok:
                warnings.append(f"Alta volatilità ({volatility:.0%})")
            
            ok, reason = self.check_order_rate()
            if not ok:
                reasons.append(reason)
            
            ok, reason = self.check_error_state()
            if not ok:
                reasons.append(reason)
            
            if reasons:
                level = GuardrailLevel.BLOCKED
                can_proceed = False
            elif warnings:
                level = GuardrailLevel.WARNING
                can_proceed = True
            else:
                level = GuardrailLevel.NORMAL
                can_proceed = True
            
            self.state.level = level
            self.state.block_reasons = reasons
            self.state.warnings = warnings
            
            return {
                "can_proceed": can_proceed,
                "level": level.value,
                "reasons": [r.value for r in reasons],
                "warnings": warnings,
                "blocked_until": self.state.blocked_until if self.state.blocked_until > time.time() else 0
            }
    
    def get_auto_green_delay(self, bet_id: str) -> float:
        """
        Ritorna il delay rimanente prima che auto-green possa attivarsi.
        
        Args:
            bet_id: ID ordine
            
        Returns:
            Secondi rimanenti (0 se può procedere)
        """
        can_green, remaining = self.check_auto_green_grace(bet_id)
        return remaining if not can_green else 0.0
    
    def reset(self):
        """Reset dello stato guardrail."""
        with self._lock:
            self.state = GuardrailState()
            self._pending_auto_green.clear()
            logger.info("[GUARDRAIL] Reset eseguito")
    
    def get_status(self) -> Dict:
        """Ritorna stato corrente del guardrail."""
        with self._lock:
            now = time.time()
            recent_orders = [o for o in self.state.order_history 
                           if o.timestamp > now - 60.0]
            
            return {
                "level": self.state.level.value,
                "consecutive_errors": self.state.consecutive_errors,
                "orders_last_minute": len(recent_orders),
                "pending_auto_green": len(self._pending_auto_green),
                "blocked_until": self.state.blocked_until if self.state.blocked_until > now else 0,
                "warnings": self.state.warnings,
                "block_reasons": [r.value for r in self.state.block_reasons]
            }
    
    def set_manual_block(self, blocked: bool):
        """
        Imposta blocco manuale.
        
        Args:
            blocked: True per bloccare, False per sbloccare
        """
        with self._lock:
            if blocked:
                self.state.block_reasons.append(BlockReason.MANUAL_BLOCK)
                self.state.level = GuardrailLevel.BLOCKED
            else:
                self.state.block_reasons = [r for r in self.state.block_reasons 
                                            if r != BlockReason.MANUAL_BLOCK]
                if not self.state.block_reasons:
                    self.state.level = GuardrailLevel.NORMAL


_global_guardrail: Optional[AIGuardrail] = None


def get_guardrail() -> AIGuardrail:
    """Ritorna istanza globale AI Guardrail."""
    global _global_guardrail
    if _global_guardrail is None:
        _global_guardrail = AIGuardrail()
    return _global_guardrail
