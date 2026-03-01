"""
Test Telemetria Liquidity Guard e UI Indicator v3.68

Verifica:
- SafetyLogger registra eventi LIQUIDITY_BLOCK e LIQUIDITY_WARNING
- evaluate_runner_liquidity restituisce status corretti
- Integrazione con controller per telemetria automatica
"""

import unittest
from unittest.mock import Mock, patch

from safety_logger import (
    SafetyLogger, 
    SafetyEventType,
    evaluate_runner_liquidity,
    LiquidityStatus,
    get_safety_logger
)


class TestEvaluateRunnerLiquidity(unittest.TestCase):
    """Test funzione evaluate_runner_liquidity (allineata con Liquidity Guard)."""
    
    def test_ok_status_high_liquidity(self):
        """Liquidita >= required*multiplier → status OK (verde)."""
        result = evaluate_runner_liquidity(
            stake=10.0,
            available_liquidity=100.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=50.0
        )
        
        self.assertEqual(result["status"], LiquidityStatus.OK)
        self.assertEqual(result["color"], "#4CAF50")
        self.assertGreaterEqual(result["ratio"], 1.0)
    
    def test_borderline_status_warning_mode(self):
        """Liquidita < required ma >= 40% in warning mode → BORDERLINE (giallo)."""
        result = evaluate_runner_liquidity(
            stake=10.0,
            available_liquidity=20.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=10.0,
            warning_only=True
        )
        
        self.assertEqual(result["status"], LiquidityStatus.BORDERLINE)
        self.assertEqual(result["color"], "#FFC107")
        self.assertGreaterEqual(result["ratio"], 0.4)
        self.assertLess(result["ratio"], 1.0)
        self.assertFalse(result["will_block"])
    
    def test_borderline_becomes_dry_when_blocking(self):
        """Liquidita < required in blocking mode → DRY (rosso)."""
        result = evaluate_runner_liquidity(
            stake=10.0,
            available_liquidity=20.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=10.0,
            warning_only=False
        )
        
        self.assertEqual(result["status"], LiquidityStatus.DRY)
        self.assertEqual(result["color"], "#F44336")
        self.assertTrue(result["will_block"])
    
    def test_very_low_ratio_warning_mode_stays_borderline(self):
        """Liquidita molto bassa ma warning_only=True → BORDERLINE (giallo, non blocca)."""
        result = evaluate_runner_liquidity(
            stake=100.0,
            available_liquidity=80.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=50.0,
            warning_only=True
        )
        
        self.assertEqual(result["status"], LiquidityStatus.BORDERLINE)
        self.assertEqual(result["color"], "#FFC107")
        self.assertFalse(result["will_block"])
    
    def test_dry_status_low_liquidity(self):
        """Liquidita < 40% required → status DRY (rosso)."""
        result = evaluate_runner_liquidity(
            stake=100.0,
            available_liquidity=100.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=50.0
        )
        
        self.assertEqual(result["status"], LiquidityStatus.DRY)
        self.assertEqual(result["color"], "#F44336")
        self.assertLess(result["ratio"], 0.4)
    
    def test_zero_stake_is_ok(self):
        """Stake zero → sempre OK."""
        result = evaluate_runner_liquidity(
            stake=0.0,
            available_liquidity=10.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=5.0
        )
        
        self.assertEqual(result["status"], LiquidityStatus.OK)
    
    def test_lay_uses_liability(self):
        """LAY valuta liquidita vs liability*multiplier."""
        result = evaluate_runner_liquidity(
            stake=10.0,
            available_liquidity=60.0,
            side="LAY",
            price=3.0,
            multiplier=3.0,
            min_absolute=50.0
        )
        
        self.assertEqual(result["status"], LiquidityStatus.OK)
    
    def test_tooltip_contains_values(self):
        """Tooltip contiene valori liquidita e richiesto."""
        result = evaluate_runner_liquidity(
            stake=50.0,
            available_liquidity=200.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=50.0
        )
        
        self.assertIn("Liquidita", result["tooltip"])
        self.assertIn("200", result["tooltip"])
    
    def test_below_min_absolute_is_dry(self):
        """Liquidita sotto minimo assoluto → DRY."""
        result = evaluate_runner_liquidity(
            stake=10.0,
            available_liquidity=40.0,
            side="BACK",
            price=2.0,
            multiplier=3.0,
            min_absolute=50.0
        )
        
        self.assertEqual(result["status"], LiquidityStatus.DRY)
        self.assertIn("< min", result["tooltip"])


class TestSafetyLoggerLiquidity(unittest.TestCase):
    """Test metodi log_liquidity_block e log_liquidity_warning."""
    
    def setUp(self):
        self.logger = get_safety_logger()
    
    @patch.object(SafetyLogger, 'log_event')
    def test_log_liquidity_block_calls_log_event(self, mock_log):
        """log_liquidity_block chiama log_event con tipo corretto."""
        self.logger.log_liquidity_block(
            market_id="1.123456",
            selection_id=12345,
            runner_name="Test Runner",
            stake=100.0,
            available_liquidity=50.0,
            required_liquidity=300.0,
            side="BACK",
            reason="INSUFFICIENT_LIQUIDITY",
            simulation=False
        )
        
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        self.assertEqual(call_args[0][0], SafetyEventType.LIQUIDITY_BLOCK)
    
    @patch.object(SafetyLogger, 'log_event')
    def test_log_liquidity_warning_calls_log_event(self, mock_log):
        """log_liquidity_warning chiama log_event con tipo corretto."""
        self.logger.log_liquidity_warning(
            market_id="1.123456",
            selection_id=12345,
            runner_name="Test Runner",
            stake=100.0,
            available_liquidity=200.0,
            required_liquidity=300.0,
            side="BACK",
            simulation=True
        )
        
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        self.assertEqual(call_args[0][0], SafetyEventType.LIQUIDITY_WARNING)


class TestControllerTelemetry(unittest.TestCase):
    """Test integrazione telemetria nel controller."""
    
    def setUp(self):
        self.mock_broker = Mock()
        self.mock_pnl = Mock()
    
    @patch('controllers.dutching_controller.LIQUIDITY_GUARD_ENABLED', True)
    @patch('controllers.dutching_controller.LIQUIDITY_MULTIPLIER', 3.0)
    @patch('controllers.dutching_controller.MIN_LIQUIDITY_ABSOLUTE', 50.0)
    @patch('controllers.dutching_controller.LIQUIDITY_WARNING_ONLY', False)
    def test_block_triggers_telemetry(self):
        """Blocco liquidity guard registra evento."""
        from controllers.dutching_controller import DutchingController
        
        controller = DutchingController(
            broker=self.mock_broker,
            pnl_engine=self.mock_pnl,
            simulation=True
        )
        
        with patch.object(controller.safety_logger, 'log_liquidity_block') as mock_log:
            selections = [{
                "selectionId": 1,
                "runnerName": "Low Liq",
                "price": 2.0,
                "stake": 100.0,
                "back_ladder": [{"price": 2.0, "size": 60.0}],
                "lay_ladder": [{"price": 2.02, "size": 60.0}]
            }]
            
            controller._check_liquidity_guard(selections, "BACK", "1.123")
            
            mock_log.assert_called()


class TestLiquidityStatusEnum(unittest.TestCase):
    """Test classe LiquidityStatus."""
    
    def test_status_values(self):
        """Verifica valori status."""
        self.assertEqual(LiquidityStatus.OK, "OK")
        self.assertEqual(LiquidityStatus.BORDERLINE, "BORDERLINE")
        self.assertEqual(LiquidityStatus.DRY, "DRY")


if __name__ == "__main__":
    unittest.main()
