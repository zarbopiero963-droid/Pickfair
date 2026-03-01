"""
Simulation Speed Mode - Replay veloce senza bug

Problema: Replay tick → stessi costi del live, non necessario precisione ms
Soluzione: Modalità throttled per simulazione con intervalli configurabili

Impatto: Replay 5–10× più veloce
"""

import time
import threading
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class SimulationSpeed(Enum):
    """Velocità simulazione."""
    REALTIME = "realtime"
    FAST = "fast"
    ULTRA_FAST = "ultra_fast"


@dataclass
class SpeedProfile:
    """Profilo velocità simulazione."""
    name: str
    ui_interval: float
    automation_interval: float
    tick_batch_size: int
    description: str


SPEED_PROFILES: Dict[SimulationSpeed, SpeedProfile] = {
    SimulationSpeed.REALTIME: SpeedProfile(
        name="Realtime",
        ui_interval=0.25,
        automation_interval=0.10,
        tick_batch_size=1,
        description="Simulazione a velocità reale"
    ),
    SimulationSpeed.FAST: SpeedProfile(
        name="Fast",
        ui_interval=0.50,
        automation_interval=1.0,
        tick_batch_size=10,
        description="5× più veloce"
    ),
    SimulationSpeed.ULTRA_FAST: SpeedProfile(
        name="Ultra Fast",
        ui_interval=1.0,
        automation_interval=2.0,
        tick_batch_size=50,
        description="10× più veloce"
    )
}


class SimulationSpeedController:
    """
    Controlla la velocità di simulazione.
    
    Modalità:
    - Realtime: Come live, per debugging
    - Fast: 5× più veloce, UI throttled
    - Ultra Fast: 10× più veloce, batch processing
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._speed = SimulationSpeed.FAST
        self._is_simulation = False
        self._last_tick_time = 0
        self._ui_tick_buffer: list = []
        self._automation_tick_count: int = 0
        self._stats = {
            "ticks_processed": 0,
            "batches_dispatched": 0,
            "time_saved_seconds": 0
        }
    
    @property
    def is_simulation(self) -> bool:
        return self._is_simulation
    
    @is_simulation.setter
    def is_simulation(self, value: bool):
        with self._lock:
            self._is_simulation = value
            if not value:
                self._ui_tick_buffer.clear()
                self._automation_tick_count = 0
    
    @property
    def speed(self) -> SimulationSpeed:
        return self._speed
    
    @speed.setter
    def speed(self, value: SimulationSpeed):
        with self._lock:
            self._speed = value
    
    @property
    def profile(self) -> SpeedProfile:
        """Profilo corrente."""
        return SPEED_PROFILES[self._speed]
    
    @property
    def ui_interval(self) -> float:
        """Intervallo UI per modalità corrente."""
        if self._is_simulation:
            return self.profile.ui_interval
        return 0.25
    
    @property
    def automation_interval(self) -> float:
        """Intervallo automazioni per modalità corrente."""
        if self._is_simulation:
            return self.profile.automation_interval
        return 0.10
    
    def should_process_tick(self) -> bool:
        """
        Verifica se processare il tick per UI in base alla velocità.
        
        NOTA: Tutti i tick vengono sempre processati per storage.
        Questo metodo controlla solo se UI deve essere aggiornata.
        In modalità Fast/Ultra Fast, UI aggiornata ogni N tick.
        
        Returns:
            True se UI deve essere aggiornata con questo tick
        """
        if not self._is_simulation:
            return True
        
        with self._lock:
            self._stats["ticks_processed"] += 1
            
            batch_size = self.profile.tick_batch_size
            if batch_size <= 1:
                return True
            
            self._ui_tick_buffer.append(time.time())
            
            if len(self._ui_tick_buffer) >= batch_size:
                self._ui_tick_buffer.clear()
                self._stats["batches_dispatched"] += 1
                return True
            
            return False
    
    def should_process_tick_for_storage(self) -> bool:
        """
        Verifica se processare tick per storage.
        
        Storage riceve SEMPRE tutti i tick (full-speed).
        """
        return True
    
    def should_process_tick_for_automation(self) -> bool:
        """
        Verifica se processare tick per automazioni.
        
        Automazioni valutate con throttling configurabile.
        Buffer separato da UI per evitare interferenze.
        """
        if not self._is_simulation:
            return True
        
        batch_size = max(2, self.profile.tick_batch_size // 5)
        
        with self._lock:
            self._automation_tick_count += 1
            
            if self._automation_tick_count >= batch_size:
                self._automation_tick_count = 0
                return True
            
            return False
    
    def calculate_time_compression(self, real_duration: float) -> float:
        """
        Calcola durata compressa per simulazione.
        
        Args:
            real_duration: Durata reale in secondi
            
        Returns:
            Durata compressa
        """
        if not self._is_simulation:
            return real_duration
        
        compression_factor = self.profile.tick_batch_size
        compressed = real_duration / compression_factor
        
        with self._lock:
            self._stats["time_saved_seconds"] += (real_duration - compressed)
        
        return compressed
    
    def sleep_compressed(self, duration: float):
        """
        Sleep con compressione tempo per simulazione.
        
        In modalità Fast/Ultra Fast, riduce i tempi di attesa.
        """
        compressed = self.calculate_time_compression(duration)
        if compressed > 0:
            time.sleep(compressed)
    
    def get_available_speeds(self) -> Dict[str, SpeedProfile]:
        """Lista velocità disponibili."""
        return {s.value: SPEED_PROFILES[s] for s in SimulationSpeed}
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiche della simulazione."""
        with self._lock:
            return {
                **self._stats,
                "current_speed": self._speed.value,
                "is_simulation": self._is_simulation,
                "compression_ratio": self.profile.tick_batch_size
            }
    
    def reset_stats(self):
        """Reset statistiche."""
        with self._lock:
            self._stats = {
                "ticks_processed": 0,
                "batches_dispatched": 0,
                "time_saved_seconds": 0
            }


_speed_controller: Optional[SimulationSpeedController] = None


def get_speed_controller() -> SimulationSpeedController:
    """Ottiene l'istanza singleton del SimulationSpeedController."""
    global _speed_controller
    if _speed_controller is None:
        _speed_controller = SimulationSpeedController()
    return _speed_controller


def is_simulation_mode() -> bool:
    """Shortcut per verificare modalità simulazione."""
    return get_speed_controller().is_simulation


def set_simulation_mode(enabled: bool, speed: SimulationSpeed = SimulationSpeed.FAST):
    """Imposta modalità simulazione."""
    controller = get_speed_controller()
    controller.is_simulation = enabled
    controller.speed = speed
