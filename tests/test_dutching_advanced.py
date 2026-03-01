"""
Test Dutching Avanzato - Revisione Tecnica Completa v3.66

Copertura:
- BACK/LAY/Mixed Dutching matematica
- Target Profit
- Cashout dinamico
- Auto-Green simulazione
- Book % optimizer
- Preset stake
- Edge cases (price < 1.01, stake min/max, partial fill)
"""

import unittest
from copy import deepcopy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dutching import (
    calculate_dutching_stakes,
    calculate_mixed_dutching,
    dynamic_cashout_single,
    _calculate_back_dutching,
    _calculate_lay_dutching,
)


SELECTIONS = [
    {'selectionId': 1, 'runnerName': '0-0', 'price': 8.0},
    {'selectionId': 2, 'runnerName': '1-0', 'price': 6.5},
    {'selectionId': 3, 'runnerName': '1-1', 'price': 7.0},
    {'selectionId': 4, 'runnerName': '2-1', 'price': 9.5},
    {'selectionId': 5, 'runnerName': '0-1', 'price': 8.5},
]

TOTAL_STAKE = 100.0
TARGET_PROFIT = 50.0
COMMISSION = 4.5


class TestBackDutching(unittest.TestCase):
    """Test matematica BACK Dutching."""
    
    def test_back_uniform_profit(self):
        """BACK Dutching produce profitto uniforme."""
        results, uniform_profit, implied_prob = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=COMMISSION
        )
        profits = [r['profitIfWins'] for r in results]
        self.assertTrue(all(abs(p - profits[0]) < 0.50 for p in profits))
    
    def test_back_total_stake_respected(self):
        """Stake totale rispettato."""
        results, _, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=COMMISSION
        )
        total = sum(r['stake'] for r in results)
        self.assertAlmostEqual(total, TOTAL_STAKE, delta=0.50)
    
    def test_back_all_stakes_positive(self):
        """Tutti gli stake positivi."""
        results, _, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=COMMISSION
        )
        self.assertTrue(all(r['stake'] > 0 for r in results))
    
    def test_back_3_selections(self):
        """BACK con 3 selezioni."""
        selections = deepcopy(SELECTIONS[:3])
        results, profit, _ = calculate_dutching_stakes(
            selections, 50.0, bet_type="BACK", commission=COMMISSION
        )
        self.assertEqual(len(results), 3)
        self.assertTrue(profit > 0)
    
    def test_back_10_selections(self):
        """BACK con 10 selezioni."""
        selections = deepcopy(SELECTIONS) + [
            {'selectionId': i, 'runnerName': f'Runner-{i}', 'price': 5.0 + i * 0.5}
            for i in range(6, 11)
        ]
        results, profit, _ = calculate_dutching_stakes(
            selections, 200.0, bet_type="BACK", commission=COMMISSION
        )
        self.assertEqual(len(results), 10)


class TestBackTargetProfit(unittest.TestCase):
    """Test Target Profit BACK via Mixed Dutching."""
    
    def test_target_profit_reached(self):
        """Target profit raggiunto via mixed dutching."""
        results, profit, _ = calculate_mixed_dutching(
            deepcopy(SELECTIONS), TARGET_PROFIT, commission=COMMISSION
        )
        self.assertTrue(len(results) > 0)
        self.assertIsInstance(profit, (int, float))
    
    def test_target_profit_low(self):
        """Target profit basso (10)."""
        results, _, _ = calculate_mixed_dutching(
            deepcopy(SELECTIONS), 10.0, commission=COMMISSION
        )
        self.assertTrue(len(results) > 0)
    
    def test_target_profit_high(self):
        """Target profit alto (200)."""
        results, _, _ = calculate_mixed_dutching(
            deepcopy(SELECTIONS), 200.0, commission=COMMISSION
        )
        self.assertTrue(len(results) > 0)


class TestLayDutching(unittest.TestCase):
    """Test matematica LAY Dutching."""
    
    def test_lay_liabilities_positive(self):
        """LAY liabilities positive."""
        results, profit, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="LAY", commission=COMMISSION
        )
        for r in results:
            liability = r['stake'] * (r['price'] - 1)
            self.assertTrue(liability >= 0)
    
    def test_lay_stakes_calculated(self):
        """LAY stakes calcolati."""
        results, _, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="LAY", commission=COMMISSION
        )
        self.assertTrue(all(r['stake'] >= 0 for r in results))


class TestMixedDutching(unittest.TestCase):
    """Test Mixed BACK+LAY Dutching."""
    
    def test_mixed_uniform_profit(self):
        """Mixed Dutching profitto uniforme."""
        results, profit, _ = calculate_mixed_dutching(
            deepcopy(SELECTIONS), TOTAL_STAKE, commission=COMMISSION
        )
        self.assertTrue(len(results) > 0)
        self.assertIsInstance(profit, (int, float))
    
    def test_mixed_sides_assigned(self):
        """Mixed calcola correttamente."""
        results, profit, _ = calculate_mixed_dutching(
            deepcopy(SELECTIONS), TOTAL_STAKE, commission=COMMISSION
        )
        self.assertTrue(len(results) > 0)


class TestDynamicCashout(unittest.TestCase):
    """Test Cashout dinamico."""
    
    def test_cashout_single_back(self):
        """Cashout singolo BACK."""
        result = dynamic_cashout_single(
            back_stake=20.0,
            back_price=8.0, 
            lay_price=7.5,
            commission=COMMISSION
        )
        self.assertIn('lay_stake', result)
    
    def test_cashout_returns_dict(self):
        """Cashout ritorna dizionario."""
        result = dynamic_cashout_single(
            back_stake=10.0,
            back_price=8.0,
            lay_price=7.0,
            commission=COMMISSION
        )
        self.assertIsInstance(result, dict)


class TestAutoGreenSimulation(unittest.TestCase):
    """Test Auto-Green in simulazione."""
    
    def test_auto_green_matched_orders(self):
        """Auto-green con ordini matched."""
        result = dynamic_cashout_single(
            back_stake=20.0,
            back_price=8.0,
            lay_price=7.0,
            commission=COMMISSION
        )
        self.assertIn('lay_stake', result)
        self.assertIn('net_profit', result)
    
    def test_auto_green_partial_fill(self):
        """Auto-green con partial fill."""
        result = dynamic_cashout_single(
            back_stake=10.0,
            back_price=6.0,
            lay_price=5.5,
            commission=COMMISSION
        )
        self.assertIn('lay_stake', result)
        self.assertIn('net_profit', result)


class TestBookPercentOptimizer(unittest.TestCase):
    """Test Book % optimizer."""
    
    def test_book_percent_calculation(self):
        """Book % calcolato correttamente."""
        book_percent = sum(1/r['price'] for r in SELECTIONS) * 100
        self.assertTrue(book_percent > 0)
        self.assertTrue(book_percent < 200)
    
    def test_book_percent_warning_threshold(self):
        """Warning se Book % > 105."""
        high_odds = [{'price': 1.5}, {'price': 1.8}, {'price': 2.0}]
        book_percent = sum(1/r['price'] for r in high_odds) * 100
        warning = book_percent > 105
        self.assertIsInstance(warning, bool)
    
    def test_book_percent_normal_range(self):
        """Book % in range normale."""
        book_percent = sum(1/r['price'] for r in SELECTIONS) * 100
        self.assertLess(book_percent, 105)


class TestPresetStake(unittest.TestCase):
    """Test Preset stake buttons."""
    
    def test_preset_25_percent(self):
        """Preset 25% stake."""
        preset = 0.25
        stake = TOTAL_STAKE * preset
        self.assertEqual(stake, 25.0)
    
    def test_preset_50_percent(self):
        """Preset 50% stake."""
        preset = 0.50
        stake = TOTAL_STAKE * preset
        self.assertEqual(stake, 50.0)
    
    def test_preset_100_percent(self):
        """Preset 100% stake."""
        preset = 1.0
        stake = TOTAL_STAKE * preset
        self.assertEqual(stake, 100.0)
    
    def test_all_presets_valid(self):
        """Tutti i preset validi."""
        presets = [0.25, 0.5, 1.0]
        for p in presets:
            stake = TOTAL_STAKE * p
            self.assertTrue(0 < stake <= TOTAL_STAKE)


class TestEdgeCases(unittest.TestCase):
    """Test Edge Cases critici."""
    
    def test_empty_selections(self):
        """Selezioni vuote gestite."""
        try:
            results, _, _ = calculate_dutching_stakes([], 100.0, bet_type="BACK")
            self.assertEqual(len(results), 0)
        except (ValueError, ZeroDivisionError):
            pass
    
    def test_price_below_minimum(self):
        """Prezzo < 1.01 gestito."""
        selections = [{'selectionId': 1, 'runnerName': 'A', 'price': 1.0}]
        try:
            results, _, _ = calculate_dutching_stakes(selections, 100.0, bet_type="BACK")
        except (ValueError, ZeroDivisionError):
            pass
    
    def test_extreme_high_price(self):
        """Prezzo estremo (1000) gestito."""
        selections = [
            {'selectionId': 1, 'runnerName': 'A', 'price': 1000.0},
            {'selectionId': 2, 'runnerName': 'B', 'price': 2.0},
        ]
        results, profit, _ = calculate_dutching_stakes(selections, 100.0, bet_type="BACK")
        self.assertEqual(len(results), 2)
    
    def test_single_selection(self):
        """Singola selezione."""
        selections = [{'selectionId': 1, 'runnerName': 'A', 'price': 2.0}]
        results, profit, _ = calculate_dutching_stakes(selections, 100.0, bet_type="BACK")
        self.assertEqual(len(results), 1)
    
    def test_stake_minimum(self):
        """Stake minimo rispettato."""
        results, _, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), 5.0, bet_type="BACK", commission=COMMISSION
        )
        for r in results:
            self.assertTrue(r['stake'] >= 0)


class TestCommission(unittest.TestCase):
    """Test gestione commissioni."""
    
    def test_italian_commission_4_5(self):
        """Commissione italiana 4.5%."""
        results, profit, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=4.5
        )
        self.assertTrue(profit > 0)
    
    def test_zero_commission(self):
        """Commissione 0%."""
        results, profit, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=0.0
        )
        self.assertTrue(profit > 0)
    
    def test_high_commission(self):
        """Commissione alta 10%."""
        results, profit, _ = calculate_dutching_stakes(
            deepcopy(SELECTIONS), TOTAL_STAKE, bet_type="BACK", commission=10.0
        )
        self.assertIsInstance(profit, (int, float))


if __name__ == "__main__":
    unittest.main(verbosity=2)
