"""
Auto-Throttle - Regolatore Automatico Carico Sistema.

Cos'è: Un cruise control che rallenta il sistema quando sotto stress
e lo accelera quando è libero.

Features:
    - Monitora 5 segnali: API calls/min, Replace/sec, Telegram queue, DB latency, Loop latency
    - Adatta automaticamente: polling interval, replace threshold, telegram delay
    - Non spegne nulla, solo adatta il ritmo
    - Transizioni smooth tra livelli di carico
    - Metriche dettagliate
"""

import time
import threading
import logging
from typing import Dict, Callable, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


class LoadLevel(Enum):
    """Livelli di carico sistema."""
    IDLE = "idle"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThrottleConfig:
    """Configurazione per ogni livello di carico."""
    polling_interval: float
    replace_profit_threshold: float
    telegram_delay: float
    cashout_min_profit: float
    skip_micro_updates: bool


# TUNING H24 SAFE - Valori ottimizzati per Betfair Exchange live
# Betfair "guarda" sopra 80-100 API/min - queste soglie restano safe
DEFAULT_CONFIGS = {
    LoadLevel.IDLE: ThrottleConfig(
        polling_interval=1.0,
        replace_profit_threshold=0.05,
        telegram_delay=0.3,
        cashout_min_profit=0.1,
        skip_micro_updates=False
    ),
    LoadLevel.LOW: ThrottleConfig(
        polling_interval=1.5,
        replace_profit_threshold=0.10,
        telegram_delay=0.4,
        cashout_min_profit=0.2,
        skip_micro_updates=False
    ),
    LoadLevel.NORMAL: ThrottleConfig(
        polling_interval=2.0,
        replace_profit_threshold=0.15,  # Target: replace_rate 15-30%
        telegram_delay=0.5,
        cashout_min_profit=0.3,
        skip_micro_updates=False
    ),
    LoadLevel.HIGH: ThrottleConfig(
        polling_interval=3.5,  # Aumentato da 3.0
        replace_profit_threshold=0.30,  # Meno aggressivo
        telegram_delay=0.8,
        cashout_min_profit=0.5,
        skip_micro_updates=True
    ),
    LoadLevel.CRITICAL: ThrottleConfig(
        polling_interval=5.0,
        replace_profit_threshold=1.00,  # Difesa, non profit
        telegram_delay=1.5,
        cashout_min_profit=1.0,
        skip_micro_updates=True
    )
}


@dataclass
class LoadMetrics:
    """Metriche correnti del sistema."""
    api_calls_per_min: float = 0
    replaces_per_min: float = 0
    telegram_queue_depth: int = 0
    db_latency_ms: float = 0
    loop_latency_ms: float = 0
    active_markets: int = 0
    active_orders: int = 0
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Raccoglie metriche per calcolo carico."""
    
    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self._api_calls: deque = deque()
        self._replaces: deque = deque()
        self._db_latencies: deque = deque()
        self._loop_latencies: deque = deque()
        self._lock = threading.RLock()
        
        self._telegram_queue_depth = 0
        self._active_markets = 0
        self._active_orders = 0
    
    def record_api_call(self):
        """Registra chiamata API."""
        with self._lock:
            self._api_calls.append(time.time())
            self._cleanup_old(self._api_calls)
    
    def record_replace(self):
        """Registra operazione replace."""
        with self._lock:
            self._replaces.append(time.time())
            self._cleanup_old(self._replaces)
    
    def record_db_latency(self, latency_ms: float):
        """Registra latenza DB."""
        with self._lock:
            self._db_latencies.append((time.time(), latency_ms))
            self._cleanup_old_tuples(self._db_latencies)
    
    def record_loop_latency(self, latency_ms: float):
        """Registra latenza loop principale."""
        with self._lock:
            self._loop_latencies.append((time.time(), latency_ms))
            self._cleanup_old_tuples(self._loop_latencies)
    
    def set_telegram_queue(self, depth: int):
        """Aggiorna profondita coda Telegram."""
        self._telegram_queue_depth = depth
    
    def set_active_markets(self, count: int):
        """Aggiorna numero market attivi."""
        self._active_markets = count
    
    def set_active_orders(self, count: int):
        """Aggiorna numero ordini attivi."""
        self._active_orders = count
    
    def _cleanup_old(self, q: deque):
        """Rimuove entry vecchie dalla deque."""
        cutoff = time.time() - self.window
        while q and q[0] < cutoff:
            q.popleft()
    
    def _cleanup_old_tuples(self, q: deque):
        """Rimuove tuple vecchie dalla deque."""
        cutoff = time.time() - self.window
        while q and q[0][0] < cutoff:
            q.popleft()
    
    def get_metrics(self) -> LoadMetrics:
        """Calcola metriche correnti."""
        with self._lock:
            self._cleanup_old(self._api_calls)
            self._cleanup_old(self._replaces)
            self._cleanup_old_tuples(self._db_latencies)
            self._cleanup_old_tuples(self._loop_latencies)
            
            return LoadMetrics(
                api_calls_per_min=len(self._api_calls),
                replaces_per_min=len(self._replaces),
                telegram_queue_depth=self._telegram_queue_depth,
                db_latency_ms=self._avg_latency(self._db_latencies),
                loop_latency_ms=self._avg_latency(self._loop_latencies),
                active_markets=self._active_markets,
                active_orders=self._active_orders
            )
    
    def _avg_latency(self, q: deque) -> float:
        """Calcola latenza media."""
        if not q:
            return 0.0
        return sum(lat for _, lat in q) / len(q)


class AutoThrottle:
    """
    Regolatore automatico carico sistema.
    
    Monitora metriche e adatta parametri operativi in base al carico.
    Include isteresi per evitare oscillazioni rapide tra stati.
    """
    
    # Isteresi: tempo minimo per confermare transizione (secondi)
    HYSTERESIS_UP = 5.0    # NORMAL -> HIGH: condizione deve persistere 5s
    HYSTERESIS_DOWN = 10.0  # HIGH -> NORMAL: deve migliorare per 10s
    
    def __init__(
        self,
        configs: Dict[LoadLevel, ThrottleConfig] = None,
        thresholds: Dict[str, Dict[LoadLevel, float]] = None
    ):
        """
        Args:
            configs: Configurazioni per ogni livello di carico
            thresholds: Soglie per determinare livello carico
        """
        self.configs = configs or DEFAULT_CONFIGS
        # SOGLIE H24 SAFE - Betfair inizia a "guardare" sopra 80-100/min
        self.thresholds = thresholds or {
            'api_calls_per_min': {
                LoadLevel.IDLE: 10,
                LoadLevel.LOW: 30,
                LoadLevel.NORMAL: 70,   # Target medio < 60
                LoadLevel.HIGH: 100,    # Betfair attenzione
                LoadLevel.CRITICAL: 120  # Difesa immediata
            },
            'telegram_queue_depth': {
                LoadLevel.IDLE: 0,
                LoadLevel.LOW: 3,       # Target medio < 3
                LoadLevel.NORMAL: 10,
                LoadLevel.HIGH: 25,
                LoadLevel.CRITICAL: 40
            },
            'loop_latency_ms': {
                LoadLevel.IDLE: 20,
                LoadLevel.LOW: 50,      # Target medio < 50ms
                LoadLevel.NORMAL: 100,
                LoadLevel.HIGH: 300,
                LoadLevel.CRITICAL: 500
            }
        }
        
        self.collector = MetricsCollector()
        self._current_level = LoadLevel.NORMAL
        self._current_config = self.configs[LoadLevel.NORMAL]
        self._lock = threading.RLock()
        
        self._level_history: deque = deque(maxlen=100)
        self._callbacks: List[Callable[[LoadLevel, ThrottleConfig], None]] = []
        
        self._enabled = True
        self._last_update = time.time()
        
        # Isteresi state
        self._pending_level: Optional[LoadLevel] = None
        self._pending_since: float = 0.0
    
    def enable(self):
        """Abilita auto-throttle."""
        self._enabled = True
        logger.info("[THROTTLE] Enabled")
    
    def disable(self):
        """Disabilita auto-throttle (usa config NORMAL)."""
        self._enabled = False
        self._current_level = LoadLevel.NORMAL
        self._current_config = self.configs[LoadLevel.NORMAL]
        logger.info("[THROTTLE] Disabled, using NORMAL config")
    
    def register_callback(self, callback: Callable[[LoadLevel, ThrottleConfig], None]):
        """Registra callback per cambi di livello."""
        self._callbacks.append(callback)
    
    def update(self) -> LoadLevel:
        """
        Aggiorna livello carico basato su metriche correnti.
        Applica isteresi per evitare oscillazioni rapide.
        
        Returns:
            Livello carico corrente
        """
        if not self._enabled:
            return self._current_level
        
        metrics = self.collector.get_metrics()
        raw_level = self._calculate_level(metrics)
        now = time.time()
        
        with self._lock:
            # Applica isteresi
            new_level = self._apply_hysteresis(raw_level, now)
            
            if new_level != self._current_level:
                old_level = self._current_level
                self._current_level = new_level
                self._current_config = self.configs[new_level]
                
                self._level_history.append({
                    'timestamp': now,
                    'from': old_level.value,
                    'to': new_level.value,
                    'metrics': {
                        'api_calls': metrics.api_calls_per_min,
                        'telegram_queue': metrics.telegram_queue_depth,
                        'loop_latency': metrics.loop_latency_ms
                    }
                })
                
                logger.info(f"[THROTTLE] Level changed: {old_level.value} -> {new_level.value}")
                
                for callback in self._callbacks:
                    try:
                        callback(new_level, self._current_config)
                    except Exception as e:
                        logger.error(f"[THROTTLE] Callback error: {e}")
            
            self._last_update = now
        
        return self._current_level
    
    def _apply_hysteresis(self, raw_level: LoadLevel, now: float) -> LoadLevel:
        """
        Applica isteresi per evitare ping-pong tra stati.
        
        - Salita (verso carico maggiore): richiede 5s di persistenza
        - Discesa (verso carico minore): richiede 10s di miglioramento
        """
        level_order = [LoadLevel.IDLE, LoadLevel.LOW, LoadLevel.NORMAL, LoadLevel.HIGH, LoadLevel.CRITICAL]
        current_idx = level_order.index(self._current_level)
        raw_idx = level_order.index(raw_level)
        
        # Stesso livello: reset pending
        if raw_level == self._current_level:
            self._pending_level = None
            self._pending_since = 0.0
            return self._current_level
        
        # Determina direzione e tempo richiesto
        going_up = raw_idx > current_idx
        required_time = self.HYSTERESIS_UP if going_up else self.HYSTERESIS_DOWN
        
        # CRITICAL: transizione immediata (emergenza)
        if raw_level == LoadLevel.CRITICAL:
            self._pending_level = None
            self._pending_since = 0.0
            return raw_level
        
        # Nuova transizione pendente?
        if self._pending_level != raw_level:
            self._pending_level = raw_level
            self._pending_since = now
            logger.debug(f"[THROTTLE] Pending transition: {self._current_level.value} -> {raw_level.value}")
            return self._current_level
        
        # Stessa transizione pendente: controlla tempo
        elapsed = now - self._pending_since
        if elapsed >= required_time:
            # Transizione confermata
            self._pending_level = None
            self._pending_since = 0.0
            logger.debug(f"[THROTTLE] Hysteresis passed ({elapsed:.1f}s >= {required_time}s)")
            return raw_level
        
        # Non ancora confermata
        return self._current_level
    
    def _calculate_level(self, metrics: LoadMetrics) -> LoadLevel:
        """Calcola livello carico basato su metriche."""
        levels = []
        
        for metric_name, thresholds in self.thresholds.items():
            value = getattr(metrics, metric_name, 0)
            level = self._value_to_level(value, thresholds)
            levels.append(level)
        
        level_order = [LoadLevel.IDLE, LoadLevel.LOW, LoadLevel.NORMAL, LoadLevel.HIGH, LoadLevel.CRITICAL]
        max_idx = max(level_order.index(l) for l in levels)
        return level_order[max_idx]
    
    def _value_to_level(self, value: float, thresholds: Dict[LoadLevel, float]) -> LoadLevel:
        """Converte valore in livello usando soglie."""
        level_order = [LoadLevel.IDLE, LoadLevel.LOW, LoadLevel.NORMAL, LoadLevel.HIGH, LoadLevel.CRITICAL]
        
        for level in reversed(level_order):
            if value >= thresholds.get(level, 0):
                return level
        
        return LoadLevel.IDLE
    
    def get_config(self) -> ThrottleConfig:
        """Configurazione corrente."""
        with self._lock:
            return self._current_config
    
    def get_level(self) -> LoadLevel:
        """Livello carico corrente."""
        with self._lock:
            return self._current_level
    
    def get_polling_interval(self) -> float:
        """Intervallo polling consigliato."""
        return self._current_config.polling_interval
    
    def get_replace_threshold(self) -> float:
        """Soglia profitto per replace."""
        return self._current_config.replace_profit_threshold
    
    def get_telegram_delay(self) -> float:
        """Delay Telegram consigliato."""
        return self._current_config.telegram_delay
    
    def should_skip_micro_update(self) -> bool:
        """Se saltare micro-aggiornamenti."""
        return self._current_config.skip_micro_updates
    
    def get_stats(self) -> Dict:
        """Statistiche throttle."""
        metrics = self.collector.get_metrics()
        now = time.time()
        
        # Info isteresi
        hysteresis_info = None
        if self._pending_level is not None:
            elapsed = now - self._pending_since
            level_order = [LoadLevel.IDLE, LoadLevel.LOW, LoadLevel.NORMAL, LoadLevel.HIGH, LoadLevel.CRITICAL]
            going_up = level_order.index(self._pending_level) > level_order.index(self._current_level)
            required = self.HYSTERESIS_UP if going_up else self.HYSTERESIS_DOWN
            hysteresis_info = {
                'pending_level': self._pending_level.value,
                'elapsed_seconds': round(elapsed, 1),
                'required_seconds': required,
                'direction': 'up' if going_up else 'down'
            }
        
        return {
            'enabled': self._enabled,
            'current_level': self._current_level.value,
            'config': {
                'polling_interval': self._current_config.polling_interval,
                'replace_threshold': self._current_config.replace_profit_threshold,
                'telegram_delay': self._current_config.telegram_delay,
                'cashout_min_profit': self._current_config.cashout_min_profit,
                'skip_micro_updates': self._current_config.skip_micro_updates
            },
            'metrics': {
                'api_calls_per_min': metrics.api_calls_per_min,
                'replaces_per_min': metrics.replaces_per_min,
                'telegram_queue': metrics.telegram_queue_depth,
                'db_latency_ms': round(metrics.db_latency_ms, 1),
                'loop_latency_ms': round(metrics.loop_latency_ms, 1),
                'active_markets': metrics.active_markets,
                'active_orders': metrics.active_orders
            },
            'hysteresis': hysteresis_info,
            'level_changes': list(self._level_history)[-10:]
        }


_global_throttle = None


def get_auto_throttle() -> AutoThrottle:
    """Singleton throttle globale."""
    global _global_throttle
    if _global_throttle is None:
        _global_throttle = AutoThrottle()
    return _global_throttle


def init_auto_throttle(configs: Dict[LoadLevel, ThrottleConfig] = None) -> AutoThrottle:
    """Inizializza throttle globale."""
    global _global_throttle
    _global_throttle = AutoThrottle(configs=configs)
    return _global_throttle
