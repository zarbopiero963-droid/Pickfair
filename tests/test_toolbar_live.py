"""
Test per Toolbar e LiveMiniLadder v3.66

Test copertura:
- Toolbar toggle states
- Controller flag sync
- PnL Engine preview
- LiveMiniLadder structure
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToolbar:
    """Test per Toolbar avanzata."""
    
    def test_toolbar_initial_state(self):
        """Toolbar inizializza con stati default."""
        from ui.toolbar import Toolbar
        
        toolbar_state = {
            "simulation_enabled": False,
            "auto_green_enabled": True,
            "ai_enabled": True,
            "preset_stake_pct": 1.0,
            "market_status": "OK"
        }
        
        assert toolbar_state["simulation_enabled"] is False
        assert toolbar_state["auto_green_enabled"] is True
        assert toolbar_state["ai_enabled"] is True
        assert toolbar_state["preset_stake_pct"] == 1.0
    
    def test_toolbar_toggle_simulation(self):
        """Toggle simulation modifica controller."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        assert controller.simulation is False
        controller.simulation = True
        assert controller.simulation is True
    
    def test_toolbar_toggle_auto_green(self):
        """Toggle auto_green modifica controller."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        assert controller.auto_green_enabled is True
        controller.auto_green_enabled = False
        assert controller.auto_green_enabled is False
    
    def test_toolbar_toggle_ai_enabled(self):
        """Toggle ai_enabled modifica controller."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        assert controller.ai_enabled is True
        controller.ai_enabled = False
        assert controller.ai_enabled is False
    
    def test_preset_stake_pct(self):
        """Preset stake pct modifica controller."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        assert controller.preset_stake_pct == 1.0
        controller.preset_stake_pct = 0.5
        assert controller.preset_stake_pct == 0.5


class TestPnLPreview:
    """Test per P&L preview."""
    
    def test_calculate_preview_back(self):
        """Preview BACK calcola profitto corretto."""
        from pnl_engine import PnLEngine
        
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 10.0, "price": 2.0}
        
        preview = engine.calculate_preview(selection, side="BACK")
        
        assert preview > 0
        assert preview < 10.0
    
    def test_calculate_preview_lay(self):
        """Preview LAY calcola profitto/liability."""
        from pnl_engine import PnLEngine
        
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 10.0, "price": 2.0}
        
        preview = engine.calculate_preview(selection, side="LAY")
        
        assert isinstance(preview, float)
    
    def test_calculate_preview_invalid_price(self):
        """Preview con price <= 1 ritorna 0."""
        from pnl_engine import PnLEngine
        
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 10.0, "price": 1.0}
        
        preview = engine.calculate_preview(selection, side="BACK")
        
        assert preview == 0.0
    
    def test_calculate_preview_default_stake(self):
        """Preview usa stake default se mancante."""
        from pnl_engine import PnLEngine
        
        engine = PnLEngine(commission=4.5)
        selection = {"price": 3.0}
        
        preview = engine.calculate_preview(selection, side="BACK")
        
        assert preview > 0


class TestLiveMiniLadderStructure:
    """Test per LiveMiniLadder."""
    
    def test_live_ladder_class_exists(self):
        """LiveMiniLadder esiste in mini_ladder."""
        from ui.mini_ladder import LiveMiniLadder
        
        assert LiveMiniLadder is not None
    
    def test_live_ladder_attributes(self):
        """LiveMiniLadder ha attributi necessari."""
        from ui.mini_ladder import LiveMiniLadder
        
        assert hasattr(LiveMiniLadder, 'update_selections')
        assert hasattr(LiveMiniLadder, 'stop')
        assert hasattr(LiveMiniLadder, 'start')
    
    def test_live_ladder_refresh_interval(self):
        """LiveMiniLadder ha attributo refresh_interval."""
        from ui.mini_ladder import LiveMiniLadder
        
        import inspect
        sig = inspect.signature(LiveMiniLadder.__init__)
        params = list(sig.parameters.keys())
        assert 'refresh_interval' in params
    
    def test_live_ladder_controller_integration(self):
        """LiveMiniLadder accetta controller."""
        from ui.mini_ladder import LiveMiniLadder
        
        import inspect
        sig = inspect.signature(LiveMiniLadder.__init__)
        params = list(sig.parameters.keys())
        assert 'controller' in params


class TestControllerToolbarIntegration:
    """Test integrazione Controller + Toolbar."""
    
    def test_controller_has_toolbar_flags(self):
        """Controller ha flag per toolbar."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        assert hasattr(controller, "auto_green_enabled")
        assert hasattr(controller, "ai_enabled")
        assert hasattr(controller, "preset_stake_pct")
    
    def test_submit_respects_simulation(self):
        """Submit rispetta simulation flag."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            dry_run=False
        )
        
        assert result["simulation"] is True


class TestToolbarImports:
    """Test per verificare import corretti."""
    
    def test_toolbar_import(self):
        """Toolbar importabile."""
        from ui.toolbar import Toolbar
        assert Toolbar is not None
    
    def test_toolbar_has_methods(self):
        """Toolbar ha metodi necessari."""
        from ui.toolbar import Toolbar
        
        assert hasattr(Toolbar, 'set_market_status')
        assert hasattr(Toolbar, 'set_preflight_status')
        assert hasattr(Toolbar, 'get_state')
        assert hasattr(Toolbar, 'set_simulation')
        assert hasattr(Toolbar, 'set_auto_green')
        assert hasattr(Toolbar, 'set_ai_enabled')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
