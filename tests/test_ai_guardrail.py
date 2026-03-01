"""
Test AI Guardrail - v3.67
Test del sistema di protezione automatica.
"""

import unittest
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.ai_guardrail import (
    AIGuardrail, GuardrailConfig, GuardrailLevel, BlockReason, get_guardrail
)


class TestGuardrailMarketCheck(unittest.TestCase):
    """Test controllo mercati."""
    
    def setUp(self):
        self.guardrail = AIGuardrail()
    
    def test_match_odds_ready(self):
        """MATCH_ODDS è mercato ready."""
        ok, reason = self.guardrail.check_market_ready("MATCH_ODDS")
        self.assertTrue(ok)
        self.assertIsNone(reason)
    
    def test_winner_ready(self):
        """WINNER è mercato ready."""
        ok, reason = self.guardrail.check_market_ready("WINNER")
        self.assertTrue(ok)
    
    def test_unknown_market_not_ready(self):
        """Mercato sconosciuto non ready."""
        ok, reason = self.guardrail.check_market_ready("UNKNOWN_TYPE")
        self.assertFalse(ok)
        self.assertEqual(reason, BlockReason.MARKET_NOT_READY)
    
    def test_asian_handicap_not_ready(self):
        """Asian Handicap non ready per default."""
        ok, reason = self.guardrail.check_market_ready("ASIAN_HANDICAP")
        self.assertFalse(ok)


class TestGuardrailWoMData(unittest.TestCase):
    """Test controllo dati WoM."""
    
    def setUp(self):
        self.guardrail = AIGuardrail()
    
    def test_sufficient_data(self):
        """Dati sufficienti passano."""
        ok, reason = self.guardrail.check_wom_data(tick_count=20, confidence=0.6)
        self.assertTrue(ok)
    
    def test_insufficient_ticks(self):
        """Tick insufficienti bloccano."""
        ok, reason = self.guardrail.check_wom_data(tick_count=3, confidence=0.6)
        self.assertFalse(ok)
        self.assertEqual(reason, BlockReason.INSUFFICIENT_DATA)
    
    def test_low_confidence(self):
        """Confidence bassa blocca."""
        ok, reason = self.guardrail.check_wom_data(tick_count=20, confidence=0.1)
        self.assertFalse(ok)


class TestGuardrailVolatility(unittest.TestCase):
    """Test controllo volatilità."""
    
    def setUp(self):
        self.guardrail = AIGuardrail()
    
    def test_normal_volatility(self):
        """Volatilità normale passa."""
        ok, reason = self.guardrail.check_volatility(0.3)
        self.assertTrue(ok)
    
    def test_high_volatility(self):
        """Alta volatilità blocca."""
        ok, reason = self.guardrail.check_volatility(0.9)
        self.assertFalse(ok)
        self.assertEqual(reason, BlockReason.HIGH_VOLATILITY)


class TestGuardrailAutoGreen(unittest.TestCase):
    """Test grace period auto-green."""
    
    def setUp(self):
        config = GuardrailConfig(auto_green_grace_sec=1.0)
        self.guardrail = AIGuardrail(config)
    
    def test_grace_period_active(self):
        """Grace period attivo blocca."""
        bet_id = "BET123"
        self.guardrail.register_order_for_auto_green(bet_id)
        
        can_green, remaining = self.guardrail.check_auto_green_grace(bet_id)
        
        self.assertFalse(can_green)
        self.assertGreater(remaining, 0)
    
    def test_grace_period_expired(self):
        """Grace period scaduto permette."""
        bet_id = "BET456"
        self.guardrail.register_order_for_auto_green(bet_id, placed_at=time.time() - 5.0)
        
        can_green, remaining = self.guardrail.check_auto_green_grace(bet_id)
        
        self.assertTrue(can_green)
        self.assertEqual(remaining, 0.0)
    
    def test_unknown_order(self):
        """Ordine sconosciuto può procedere."""
        can_green, remaining = self.guardrail.check_auto_green_grace("UNKNOWN")
        
        self.assertTrue(can_green)


class TestGuardrailOrderRate(unittest.TestCase):
    """Test limite ordini."""
    
    def setUp(self):
        config = GuardrailConfig(max_orders_per_minute=3)
        self.guardrail = AIGuardrail(config)
    
    def test_under_limit(self):
        """Sotto limite passa."""
        self.guardrail.record_order("MKT1", 123, "BACK", 10.0)
        self.guardrail.record_order("MKT1", 456, "LAY", 10.0)
        
        ok, reason = self.guardrail.check_order_rate()
        self.assertTrue(ok)
    
    def test_at_limit(self):
        """Al limite blocca."""
        for i in range(3):
            self.guardrail.record_order("MKT1", i, "BACK", 10.0)
        
        ok, reason = self.guardrail.check_order_rate()
        self.assertFalse(ok)
        self.assertEqual(reason, BlockReason.OVERTRADE_PROTECTION)


class TestGuardrailErrorState(unittest.TestCase):
    """Test gestione errori consecutivi."""
    
    def setUp(self):
        config = GuardrailConfig(
            consecutive_error_limit=2,
            cooldown_after_error_sec=1.0
        )
        self.guardrail = AIGuardrail(config)
    
    def test_no_errors(self):
        """Senza errori passa."""
        ok, reason = self.guardrail.check_error_state()
        self.assertTrue(ok)
    
    def test_consecutive_errors_block(self):
        """Errori consecutivi bloccano."""
        self.guardrail.record_order("MKT1", 1, "BACK", 10.0, success=False)
        self.guardrail.record_order("MKT1", 2, "BACK", 10.0, success=False)
        
        ok, reason = self.guardrail.check_error_state()
        self.assertFalse(ok)
        self.assertEqual(reason, BlockReason.CONSECUTIVE_ERRORS)
    
    def test_success_resets_counter(self):
        """Successo resetta il contatore."""
        self.guardrail.record_order("MKT1", 1, "BACK", 10.0, success=False)
        self.guardrail.record_order("MKT1", 2, "BACK", 10.0, success=True)
        
        self.assertEqual(self.guardrail.state.consecutive_errors, 0)


class TestGuardrailFullCheck(unittest.TestCase):
    """Test controllo completo."""
    
    def setUp(self):
        self.guardrail = AIGuardrail()
    
    def test_full_check_pass(self):
        """Controllo completo passa."""
        result = self.guardrail.full_check(
            market_type="MATCH_ODDS",
            tick_count=30,
            wom_confidence=0.6,
            volatility=0.3
        )
        
        self.assertTrue(result["can_proceed"])
        self.assertEqual(result["level"], "normal")
    
    def test_full_check_warning(self):
        """Controllo con warning (alta volatilità)."""
        result = self.guardrail.full_check(
            market_type="MATCH_ODDS",
            tick_count=30,
            wom_confidence=0.6,
            volatility=0.85
        )
        
        self.assertTrue(result["can_proceed"])
        self.assertEqual(result["level"], "warning")
        self.assertGreater(len(result["warnings"]), 0)
    
    def test_full_check_insufficient_data_blocks(self):
        """Dati insufficienti bloccano (non warning)."""
        result = self.guardrail.full_check(
            market_type="MATCH_ODDS",
            tick_count=7,
            wom_confidence=0.6,
            volatility=0.3
        )
        
        self.assertFalse(result["can_proceed"])
        self.assertEqual(result["level"], "blocked")
        self.assertIn("insufficient_data", result["reasons"])
    
    def test_full_check_block(self):
        """Controllo con blocco."""
        result = self.guardrail.full_check(
            market_type="UNKNOWN_MARKET",
            tick_count=2,
            wom_confidence=0.1,
            volatility=0.9
        )
        
        self.assertFalse(result["can_proceed"])
        self.assertEqual(result["level"], "blocked")


class TestGuardrailGlobal(unittest.TestCase):
    """Test istanza globale."""
    
    def test_get_guardrail(self):
        """Test singleton."""
        g1 = get_guardrail()
        g2 = get_guardrail()
        
        self.assertIs(g1, g2)
    
    def test_get_status(self):
        """Test status."""
        guardrail = get_guardrail()
        status = guardrail.get_status()
        
        self.assertIn("level", status)
        self.assertIn("consecutive_errors", status)
        self.assertIn("orders_last_minute", status)


class TestGuardrailManualBlock(unittest.TestCase):
    """Test blocco manuale."""
    
    def setUp(self):
        self.guardrail = AIGuardrail()
    
    def test_manual_block(self):
        """Blocco manuale funziona."""
        self.guardrail.set_manual_block(True)
        
        self.assertEqual(self.guardrail.state.level, GuardrailLevel.BLOCKED)
        self.assertIn(BlockReason.MANUAL_BLOCK, self.guardrail.state.block_reasons)
    
    def test_manual_unblock(self):
        """Sblocco manuale funziona."""
        self.guardrail.set_manual_block(True)
        self.guardrail.set_manual_block(False)
        
        self.assertEqual(self.guardrail.state.level, GuardrailLevel.NORMAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
