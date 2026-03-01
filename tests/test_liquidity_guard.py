"""
Test Liquidity Guard (v3.68)

Verifica il sistema di protezione liquidità che blocca ordini
quando la liquidità disponibile non è sufficiente.
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.dutching_controller import DutchingController, PreflightResult


class TestLiquidityGuardBasic(unittest.TestCase):
    """Test base per _check_liquidity_guard."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_pnl = Mock()
        self.controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_sufficient_liquidity_passes(self):
        """Con liquidità sufficiente (3x stake), passa."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 2.0,
            "stake": 10.0,
            "back_ladder": [{"price": 2.0, "size": 100.0}],
            "lay_ladder": [{"price": 2.02, "size": 80.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertTrue(is_ok)
        self.assertEqual(len(msgs), 0)
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_insufficient_liquidity_blocks(self):
        """Con liquidità insufficiente (< 3x stake), blocca."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 2.0,
            "stake": 50.0,
            "back_ladder": [{"price": 2.0, "size": 60.0}],
            "lay_ladder": [{"price": 2.02, "size": 80.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertFalse(is_ok)
        self.assertGreater(len(msgs), 0)
        self.assertIn("insufficiente", msgs[0])
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_below_absolute_minimum_blocks(self):
        """Con liquidità sotto soglia assoluta, blocca subito."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Dead Market",
            "price": 2.0,
            "stake": 5.0,
            "back_ladder": [{"price": 2.0, "size": 20.0}],
            "lay_ladder": [{"price": 2.02, "size": 30.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertFalse(is_ok)
        self.assertIn("troppo bassa", msgs[0])
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', False)
    def test_disabled_guard_passes(self):
        """Con guard disabilitato, passa sempre."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 2.0,
            "stake": 1000.0,
            "back_ladder": [{"price": 2.0, "size": 10.0}],
            "lay_ladder": []
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertTrue(is_ok)
        self.assertEqual(len(msgs), 0)


class TestLiquidityGuardLay(unittest.TestCase):
    """Test per LAY orders (controlla liability)."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_pnl = Mock()
        self.controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_lay_sufficient_liquidity(self):
        """LAY con liquidità sufficiente per liability."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 3.0,
            "stake": 10.0,
            "side": "LAY",
            "back_ladder": [{"price": 2.98, "size": 100.0}],
            "lay_ladder": [{"price": 3.0, "size": 200.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "LAY")
        
        self.assertTrue(is_ok)
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_lay_insufficient_liquidity(self):
        """LAY con liquidità insufficiente per liability blocca."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 5.0,
            "stake": 20.0,
            "side": "LAY",
            "back_ladder": [{"price": 4.98, "size": 100.0}],
            "lay_ladder": [{"price": 5.0, "size": 100.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "LAY")
        
        self.assertFalse(is_ok)


class TestLiquidityGuardMixed(unittest.TestCase):
    """Test per MIXED orders (BACK + LAY insieme)."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_pnl = Mock()
        self.controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_mixed_all_sufficient(self):
        """MIXED con liquidità sufficiente per tutti passa."""
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Back Runner",
                "price": 2.0,
                "stake": 10.0,
                "side": "BACK",
                "back_ladder": [{"price": 2.0, "size": 100.0}],
                "lay_ladder": [{"price": 2.02, "size": 80.0}]
            },
            {
                "selectionId": 2,
                "runnerName": "Lay Runner",
                "price": 4.0,
                "stake": 5.0,
                "side": "LAY",
                "back_ladder": [{"price": 3.98, "size": 100.0}],
                "lay_ladder": [{"price": 4.0, "size": 100.0}]
            }
        ]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "MIXED")
        
        self.assertTrue(is_ok)
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_mixed_one_insufficient_blocks(self):
        """MIXED con un runner insufficiente blocca tutto."""
        selections = [
            {
                "selectionId": 1,
                "runnerName": "OK Runner",
                "price": 2.0,
                "stake": 10.0,
                "side": "BACK",
                "back_ladder": [{"price": 2.0, "size": 100.0}],
                "lay_ladder": [{"price": 2.02, "size": 80.0}]
            },
            {
                "selectionId": 2,
                "runnerName": "Low Liquidity Runner",
                "price": 4.0,
                "stake": 50.0,
                "side": "LAY",
                "back_ladder": [{"price": 3.98, "size": 100.0}],
                "lay_ladder": [{"price": 4.0, "size": 60.0}]
            }
        ]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "MIXED")
        
        self.assertFalse(is_ok)


class TestLiquidityGuardWarningMode(unittest.TestCase):
    """Test per modalità warning-only."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_pnl = Mock()
        self.controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', True)
    def test_warning_mode_passes_with_messages(self):
        """In warning mode, liquidità bassa genera warning ma non blocca."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "price": 2.0,
            "stake": 50.0,
            "back_ladder": [{"price": 2.0, "size": 80.0}],
            "lay_ladder": [{"price": 2.02, "size": 80.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertFalse(is_ok)
        self.assertGreater(len(msgs), 0)
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', True)
    def test_absolute_minimum_blocks_even_warning_mode(self):
        """Sotto soglia assoluta blocca anche in warning mode."""
        selections = [{
            "selectionId": 1,
            "runnerName": "Dead Market",
            "price": 2.0,
            "stake": 5.0,
            "back_ladder": [{"price": 2.0, "size": 20.0}],
            "lay_ladder": [{"price": 2.02, "size": 30.0}]
        }]
        
        is_ok, msgs = self.controller._check_liquidity_guard(selections, "BACK")
        
        self.assertFalse(is_ok)
        self.assertIn("troppo bassa", msgs[0])


class TestLiquidityGuardSubmitDutching(unittest.TestCase):
    """Test integrazione con submit_dutching (flusso completo)."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_broker.place_order = Mock(return_value={"betId": "test123"})
        self.mock_pnl = Mock()
        self.controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_submit_blocks_on_insufficient_liquidity(self):
        """Submit dutching blocca con liquidità insufficiente."""
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Low Liq Runner",
                "price": 2.0,
                "back_ladder": [{"price": 2.0, "size": 60.0}],
                "lay_ladder": [{"price": 2.02, "size": 60.0}]
            },
            {
                "selectionId": 2,
                "runnerName": "Runner B",
                "price": 3.0,
                "back_ladder": [{"price": 3.0, "size": 60.0}],
                "lay_ladder": [{"price": 3.02, "size": 60.0}]
            }
        ]
        
        result = self.controller.submit_dutching(
            market_id="1.123456",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100.0,
            mode="BACK"
        )
        
        self.assertEqual(result["status"], "PREFLIGHT_FAILED")
        self.assertFalse(result["preflight"]["liquidity_guard_ok"])
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_submit_passes_with_sufficient_liquidity(self):
        """Submit dutching passa con liquidità sufficiente."""
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Runner A",
                "price": 2.0,
                "back_ladder": [{"price": 2.0, "size": 500.0}],
                "lay_ladder": [{"price": 2.02, "size": 500.0}]
            },
            {
                "selectionId": 2,
                "runnerName": "Runner B",
                "price": 3.0,
                "back_ladder": [{"price": 3.0, "size": 500.0}],
                "lay_ladder": [{"price": 3.02, "size": 500.0}]
            }
        ]
        
        result = self.controller.submit_dutching(
            market_id="1.123456",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=20.0,
            mode="BACK"
        )
        
        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["preflight"]["liquidity_guard_ok"])


if __name__ == "__main__":
    unittest.main()
