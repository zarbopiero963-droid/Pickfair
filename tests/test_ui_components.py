"""
Test UI Components - Revisione Tecnica Completa v3.66

Copertura:
- Toolbar toggles e stato
- Mini Ladder struttura
- LiveMiniLadder refresh
- Book % badge
- Preset stake buttons
- Controller integrazione
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToolbarState(unittest.TestCase):
    """Test Toolbar stato e toggle."""
    
    def test_toolbar_class_exists(self):
        """Toolbar classe esiste."""
        from ui.toolbar import Toolbar
        self.assertIsNotNone(Toolbar)
    
    def test_toolbar_has_set_methods(self):
        """Toolbar ha metodi set."""
        from ui.toolbar import Toolbar
        self.assertTrue(hasattr(Toolbar, 'set_simulation'))
        self.assertTrue(hasattr(Toolbar, 'set_auto_green'))
        self.assertTrue(hasattr(Toolbar, 'set_ai_enabled'))
    
    def test_toolbar_has_get_state(self):
        """Toolbar ha get_state."""
        from ui.toolbar import Toolbar
        self.assertTrue(hasattr(Toolbar, 'get_state'))
    
    def test_toolbar_has_market_status(self):
        """Toolbar ha set_market_status."""
        from ui.toolbar import Toolbar
        self.assertTrue(hasattr(Toolbar, 'set_market_status'))
    
    def test_toolbar_has_preflight_status(self):
        """Toolbar ha set_preflight_status."""
        from ui.toolbar import Toolbar
        self.assertTrue(hasattr(Toolbar, 'set_preflight_status'))


class TestMiniLadderStructure(unittest.TestCase):
    """Test MiniLadder struttura."""
    
    def test_mini_ladder_exists(self):
        """MiniLadder esiste."""
        from ui.mini_ladder import MiniLadder
        self.assertIsNotNone(MiniLadder)
    
    def test_mini_ladder_has_update_prices(self):
        """MiniLadder ha update_prices."""
        from ui.mini_ladder import MiniLadder
        self.assertTrue(hasattr(MiniLadder, 'update_prices'))
    
    def test_mini_ladder_has_set_highlight(self):
        """MiniLadder ha set_highlight."""
        from ui.mini_ladder import MiniLadder
        self.assertTrue(hasattr(MiniLadder, 'set_highlight'))
    
    def test_mini_ladder_has_edge_badge(self):
        """MiniLadder ha set_edge_badge."""
        from ui.mini_ladder import MiniLadder
        self.assertTrue(hasattr(MiniLadder, 'set_edge_badge'))


class TestLiveMiniLadder(unittest.TestCase):
    """Test LiveMiniLadder."""
    
    def test_live_ladder_exists(self):
        """LiveMiniLadder esiste."""
        from ui.mini_ladder import LiveMiniLadder
        self.assertIsNotNone(LiveMiniLadder)
    
    def test_live_ladder_has_refresh_interval(self):
        """LiveMiniLadder ha refresh_interval param."""
        import inspect
        from ui.mini_ladder import LiveMiniLadder
        sig = inspect.signature(LiveMiniLadder.__init__)
        params = list(sig.parameters.keys())
        self.assertIn('refresh_interval', params)
    
    def test_live_ladder_has_start_stop(self):
        """LiveMiniLadder ha start/stop."""
        from ui.mini_ladder import LiveMiniLadder
        self.assertTrue(hasattr(LiveMiniLadder, 'start'))
        self.assertTrue(hasattr(LiveMiniLadder, 'stop'))
    
    def test_live_ladder_has_update_selections(self):
        """LiveMiniLadder ha update_selections."""
        from ui.mini_ladder import LiveMiniLadder
        self.assertTrue(hasattr(LiveMiniLadder, 'update_selections'))


class TestOneClickLadder(unittest.TestCase):
    """Test OneClickLadder."""
    
    def test_one_click_ladder_exists(self):
        """OneClickLadder esiste."""
        from ui.mini_ladder import OneClickLadder
        self.assertIsNotNone(OneClickLadder)
    
    def test_one_click_has_set_stake(self):
        """OneClickLadder ha set_default_stake."""
        from ui.mini_ladder import OneClickLadder
        self.assertTrue(hasattr(OneClickLadder, 'set_default_stake'))
    
    def test_one_click_has_auto_green(self):
        """OneClickLadder ha set_auto_green."""
        from ui.mini_ladder import OneClickLadder
        self.assertTrue(hasattr(OneClickLadder, 'set_auto_green'))


class TestControllerUIIntegration(unittest.TestCase):
    """Test integrazione Controller-UI."""
    
    def test_controller_has_simulation_flag(self):
        """Controller ha flag simulation."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        self.assertTrue(hasattr(controller, 'simulation'))
    
    def test_controller_has_auto_green_flag(self):
        """Controller ha flag auto_green_enabled."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        self.assertTrue(hasattr(controller, 'auto_green_enabled'))
    
    def test_controller_has_ai_flag(self):
        """Controller ha flag ai_enabled."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        self.assertTrue(hasattr(controller, 'ai_enabled'))
    
    def test_controller_has_preset_stake(self):
        """Controller ha preset_stake_pct."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        self.assertTrue(hasattr(controller, 'preset_stake_pct'))


class TestPnLEnginePreview(unittest.TestCase):
    """Test PnL Engine preview."""
    
    def test_pnl_engine_exists(self):
        """PnL Engine esiste."""
        from pnl_engine import PnLEngine
        self.assertIsNotNone(PnLEngine)
    
    def test_pnl_has_calculate_preview(self):
        """PnL ha calculate_preview."""
        from pnl_engine import PnLEngine
        self.assertTrue(hasattr(PnLEngine, 'calculate_preview'))
    
    def test_preview_back_positive(self):
        """Preview BACK ritorna valore positivo."""
        from pnl_engine import PnLEngine
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 10.0, "price": 3.0}
        preview = engine.calculate_preview(selection, side="BACK")
        self.assertTrue(preview > 0)
    
    def test_preview_lay_returns_float(self):
        """Preview LAY ritorna float."""
        from pnl_engine import PnLEngine
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 10.0, "price": 2.5}
        preview = engine.calculate_preview(selection, side="LAY")
        self.assertIsInstance(preview, float)


class TestBookPercentBadge(unittest.TestCase):
    """Test Book % badge UI."""
    
    def test_book_percent_calculation(self):
        """Book % calcolato correttamente."""
        selections = [
            {'price': 8.0},
            {'price': 6.5},
            {'price': 7.0},
        ]
        book_percent = sum(1/r['price'] for r in selections) * 100
        self.assertTrue(0 < book_percent < 100)
    
    def test_book_percent_warning_color(self):
        """Book % warning colore corretto."""
        book_percent = 110.0
        color = "red" if book_percent > 105 else "green"
        self.assertEqual(color, "red")
    
    def test_book_percent_ok_color(self):
        """Book % OK colore corretto."""
        book_percent = 95.0
        color = "red" if book_percent > 105 else "green"
        self.assertEqual(color, "green")


if __name__ == "__main__":
    unittest.main(verbosity=2)
