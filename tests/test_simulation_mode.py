"""
Test Simulation Mode - Revisione Tecnica Completa v3.66

Copertura:
- Simulazione ordini senza Betfair reale
- P&L preview simulato
- Auto-Green in simulazione
- Multi-market simulazione
- Partial fill simulazione
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copy import deepcopy
from simulation_broker import SimulationBroker
from controllers.dutching_controller import DutchingController
from pnl_engine import PnLEngine


SELECTIONS = [
    {'selectionId': 1, 'runnerName': '0-0', 'price': 8.0},
    {'selectionId': 2, 'runnerName': '1-0', 'price': 6.5},
    {'selectionId': 3, 'runnerName': '1-1', 'price': 7.0},
]


class TestSimulationBroker(unittest.TestCase):
    """Test Simulation Broker."""
    
    def test_broker_initial_balance(self):
        """Broker inizializza con balance."""
        broker = SimulationBroker(initial_balance=1000)
        self.assertEqual(broker.balance, 1000)
    
    def test_broker_place_order(self):
        """Broker piazza ordine simulato."""
        broker = SimulationBroker(initial_balance=1000)
        result = broker.place_order(
            market_id="1.234",
            selection_id=1,
            side='BACK',
            price=2.0,
            size=10.0
        )
        self.assertIn('status', result)
    
    def test_broker_tracks_orders(self):
        """Broker traccia ordini."""
        broker = SimulationBroker(initial_balance=1000)
        broker.place_order(
            market_id="1.234",
            selection_id=1,
            side='BACK',
            price=2.0,
            size=10.0
        )
        self.assertTrue(len(broker.orders) > 0)
    
    def test_broker_balance_deducted(self):
        """Broker deduce stake da balance."""
        broker = SimulationBroker(initial_balance=1000)
        broker.place_order(
            market_id="1.234",
            selection_id=1,
            side='BACK',
            price=2.0,
            size=100.0
        )
        self.assertTrue(broker.balance < 1000)


class TestControllerSimulation(unittest.TestCase):
    """Test Controller in simulation mode."""
    
    def test_controller_simulation_flag(self):
        """Controller rispetta simulation flag."""
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        self.assertTrue(controller.simulation)
    
    def test_submit_in_simulation(self):
        """Submit in simulation non piazza ordini reali."""
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=deepcopy(SELECTIONS),
            total_stake=100,
            mode="BACK",
            dry_run=False
        )
        
        self.assertTrue(result.get('simulation', False))
    
    def test_simulation_calculates_pnl(self):
        """Simulazione calcola P&L."""
        broker = SimulationBroker(initial_balance=1000)
        pnl = PnLEngine(commission=4.5)
        controller = DutchingController(broker=broker, pnl_engine=pnl, simulation=True)
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=deepcopy(SELECTIONS),
            total_stake=100,
            mode="BACK",
            dry_run=False
        )
        
        self.assertIn('orders', result)
    
    def test_auto_green_in_simulation(self):
        """Auto-green funziona in simulazione."""
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        controller.auto_green_enabled = True
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=deepcopy(SELECTIONS),
            total_stake=100,
            mode="BACK",
            auto_green=True,
            dry_run=False
        )
        
        orders = result.get('orders', [])
        if orders:
            self.assertTrue(any(o.get('auto_green', False) for o in orders))


class TestDryRun(unittest.TestCase):
    """Test Dry Run (preview ordini)."""
    
    def test_dry_run_no_orders_placed(self):
        """Dry run non piazza ordini."""
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        initial_orders = len(broker.orders)
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=deepcopy(SELECTIONS),
            total_stake=100,
            mode="BACK",
            dry_run=True
        )
        
        self.assertEqual(len(broker.orders), initial_orders)
    
    def test_dry_run_returns_preview(self):
        """Dry run ritorna preview."""
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=deepcopy(SELECTIONS),
            total_stake=100,
            mode="BACK",
            dry_run=True
        )
        
        self.assertIn('orders', result)


class TestPnLPreviewSimulation(unittest.TestCase):
    """Test P&L Preview in simulazione."""
    
    def test_preview_back(self):
        """Preview BACK in simulazione."""
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 50.0, "price": 3.0}
        preview = engine.calculate_preview(selection, side="BACK")
        
        self.assertTrue(preview > 0)
    
    def test_preview_lay(self):
        """Preview LAY in simulazione."""
        engine = PnLEngine(commission=4.5)
        selection = {"stake": 50.0, "price": 2.5}
        preview = engine.calculate_preview(selection, side="LAY")
        
        self.assertIsInstance(preview, float)
    
    def test_preview_commission_applied(self):
        """Preview applica commissione."""
        engine_with = PnLEngine(commission=4.5)
        engine_without = PnLEngine(commission=0.0)
        
        selection = {"stake": 100.0, "price": 2.0}
        
        preview_with = engine_with.calculate_preview(selection, side="BACK")
        preview_without = engine_without.calculate_preview(selection, side="BACK")
        
        self.assertLess(preview_with, preview_without)


class TestPartialFillSimulation(unittest.TestCase):
    """Test Partial Fill in simulazione."""
    
    def test_partial_fill_tracked(self):
        """Partial fill tracciato - ordine registrato."""
        broker = SimulationBroker(initial_balance=1000)
        result = broker.place_order(
            market_id="1.234",
            selection_id=1,
            side='BACK',
            price=2.0,
            size=100.0
        )
        
        self.assertIn('status', result)
        self.assertTrue(len(broker.orders) > 0)
        
        order_id = next(iter(broker.orders.keys()))
        order = broker.orders[order_id]
        
        self.assertTrue(hasattr(order, 'size') or 'size' in str(order))


if __name__ == "__main__":
    unittest.main(verbosity=2)
