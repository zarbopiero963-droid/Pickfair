"""
Test WoM Time-Window Engine - v3.67
Test delle nuove funzionalità time-window analysis.
"""

import unittest
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.wom_engine import WoMEngine, WoMResult, get_wom_engine


class TestWoMTimeWindow(unittest.TestCase):
    """Test funzionalità time-window."""
    
    def setUp(self):
        self.engine = WoMEngine(window_size=100, time_window=60.0)
        self.selection_id = 12345
    
    def _populate_ticks(self, count: int, back_vol: float, lay_vol: float):
        """Helper per popolare tick."""
        for _ in range(count):
            self.engine.record_tick(
                self.selection_id,
                back_price=2.0,
                back_volume=back_vol,
                lay_price=2.02,
                lay_volume=lay_vol
            )
    
    def test_calculate_wom_window(self):
        """Test calcolo WoM su finestra specifica."""
        self._populate_ticks(20, 100.0, 50.0)
        
        wom = self.engine.calculate_wom_window(self.selection_id, 30.0)
        
        self.assertIsInstance(wom, float)
        self.assertGreater(wom, 0.5)
    
    def test_calculate_multi_window_wom(self):
        """Test WoM su multiple finestre."""
        self._populate_ticks(30, 80.0, 60.0)
        
        result = self.engine.calculate_multi_window_wom(self.selection_id)
        
        self.assertIn("wom_5s", result)
        self.assertIn("wom_15s", result)
        self.assertIn("wom_30s", result)
        self.assertIn("wom_60s", result)
    
    def test_calculate_delta_pressure(self):
        """Test calcolo delta pressione."""
        self._populate_ticks(20, 100.0, 50.0)
        
        delta = self.engine.calculate_delta_pressure(self.selection_id)
        
        self.assertIsInstance(delta, float)
        self.assertGreaterEqual(delta, -1.0)
        self.assertLessEqual(delta, 1.0)
    
    def test_calculate_momentum(self):
        """Test calcolo momentum."""
        self._populate_ticks(20, 100.0, 50.0)
        
        momentum = self.engine.calculate_momentum(self.selection_id)
        
        self.assertIsInstance(momentum, float)
        self.assertGreaterEqual(momentum, -1.0)
        self.assertLessEqual(momentum, 1.0)
    
    def test_calculate_volatility(self):
        """Test calcolo volatilità."""
        for i in range(20):
            self.engine.record_tick(
                self.selection_id,
                back_price=2.0 + (i % 3) * 0.01,
                back_volume=100.0,
                lay_price=2.02 + (i % 3) * 0.01,
                lay_volume=50.0
            )
        
        volatility = self.engine.calculate_volatility(self.selection_id)
        
        self.assertIsInstance(volatility, float)
        self.assertGreaterEqual(volatility, 0.0)
        self.assertLessEqual(volatility, 1.0)
    
    def test_calculate_enhanced_wom(self):
        """Test WoM completo con tutti gli indicatori."""
        self._populate_ticks(30, 100.0, 60.0)
        
        result = self.engine.calculate_enhanced_wom(self.selection_id)
        
        self.assertIsNotNone(result)
        self.assertIsInstance(result, WoMResult)
        self.assertIsInstance(result.wom_5s, float)
        self.assertIsInstance(result.delta_pressure, float)
        self.assertIsInstance(result.momentum, float)
        self.assertIsInstance(result.volatility, float)
    
    def test_get_time_window_signal(self):
        """Test generazione segnale trading."""
        self._populate_ticks(30, 100.0, 40.0)
        
        signal = self.engine.get_time_window_signal(self.selection_id)
        
        self.assertIn("signal", signal)
        self.assertIn("strength", signal)
        self.assertIn("side", signal)
        self.assertIn("reasoning", signal)
        self.assertIn("wom_data", signal)
    
    def test_signal_no_data(self):
        """Test segnale senza dati."""
        signal = self.engine.get_time_window_signal(99999)
        
        self.assertEqual(signal["signal"], "NO_DATA")
        self.assertEqual(signal["strength"], 0.0)
    
    def test_back_pressure_signal(self):
        """Test segnale con pressione BACK forte."""
        self._populate_ticks(50, 200.0, 50.0)
        
        signal = self.engine.get_time_window_signal(self.selection_id)
        
        self.assertIn(signal["side"], ["BACK", "NEUTRAL"])
    
    def test_lay_pressure_signal(self):
        """Test segnale con pressione LAY forte."""
        self._populate_ticks(50, 50.0, 200.0)
        
        signal = self.engine.get_time_window_signal(self.selection_id)
        
        self.assertIn(signal["side"], ["LAY", "NEUTRAL"])


class TestWoMEngineGlobal(unittest.TestCase):
    """Test istanza globale."""
    
    def test_get_wom_engine(self):
        """Test singleton pattern."""
        engine1 = get_wom_engine()
        engine2 = get_wom_engine()
        
        self.assertIs(engine1, engine2)
    
    def test_engine_stats(self):
        """Test statistiche engine."""
        engine = get_wom_engine()
        stats = engine.get_stats()
        
        self.assertIn("selections_tracked", stats)
        self.assertIn("total_ticks", stats)


if __name__ == "__main__":
    unittest.main(verbosity=2)
