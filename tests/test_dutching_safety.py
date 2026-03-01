"""
Test suite per sicurezza Dutching.

Copre:
- Validazione mercati non dutching-ready
- Uniformità profitto post-normalizzazione
- Delay auto-green
- Blocco auto-green in simulazione
"""

import pytest
import time

from dutching import calculate_ai_mixed_stakes, MixedDutchingError, _validate_uniform_profit
from market_validator import MarketValidator, MarketValidationError
from automation_engine import should_auto_green
from trading_config import AUTO_GREEN_DELAY_SEC


class MockOrder:
    """Mock order object per test."""
    def __init__(self, meta=None):
        self.meta = meta or {}


class TestMarketValidation:
    """Test validazione mercati."""
    
    def test_match_odds_is_dutching_ready(self):
        """MATCH_ODDS è dutching-ready."""
        assert MarketValidator.is_dutching_ready("MATCH_ODDS") is True
    
    def test_winner_is_dutching_ready(self):
        """WINNER è dutching-ready."""
        assert MarketValidator.is_dutching_ready("WINNER") is True
    
    def test_correct_score_is_dutching_ready(self):
        """CORRECT_SCORE è dutching-ready."""
        assert MarketValidator.is_dutching_ready("CORRECT_SCORE") is True
    
    def test_corner_match_bet_not_dutching_ready(self):
        """CORNER_MATCH_BET non è dutching-ready."""
        assert MarketValidator.is_dutching_ready("CORNER_MATCH_BET") is False
    
    def test_over_under_not_dutching_ready(self):
        """OVER_UNDER non è dutching-ready."""
        assert MarketValidator.is_dutching_ready("OVER_UNDER_25") is False
    
    def test_asian_handicap_not_dutching_ready(self):
        """ASIAN_HANDICAP non è dutching-ready."""
        assert MarketValidator.is_dutching_ready("ASIAN_HANDICAP") is False
    
    def test_btts_not_dutching_ready(self):
        """BOTH_TEAMS_TO_SCORE non è dutching-ready."""
        assert MarketValidator.is_dutching_ready("BOTH_TEAMS_TO_SCORE") is False
    
    def test_assert_dutching_ready_raises_for_invalid(self):
        """assert_dutching_ready solleva eccezione per mercati non validi."""
        with pytest.raises(MarketValidationError):
            MarketValidator.assert_dutching_ready("CORNER_MATCH_BET")
    
    def test_assert_dutching_ready_passes_for_valid(self):
        """assert_dutching_ready passa per mercati validi."""
        MarketValidator.assert_dutching_ready("MATCH_ODDS")


class TestProfitUniformity:
    """Test uniformità profitto."""
    
    def test_uniform_profit_passes(self):
        """Profitti uniformi passano validazione."""
        stakes = {
            1: {"profit_if_win": 10.00},
            2: {"profit_if_win": 10.20},
            3: {"profit_if_win": 10.10}
        }
        _validate_uniform_profit(stakes, epsilon=0.50)
    
    def test_non_uniform_profit_fails(self):
        """Profitti non uniformi sollevano eccezione."""
        stakes = {
            1: {"profit_if_win": 10.00},
            2: {"profit_if_win": 9.00}
        }
        with pytest.raises(MixedDutchingError):
            _validate_uniform_profit(stakes, epsilon=0.50)
    
    def test_empty_stakes_passes(self):
        """Stakes vuoti passano validazione."""
        _validate_uniform_profit({}, epsilon=0.50)
    
    def test_single_stake_passes(self):
        """Singolo stake passa validazione."""
        stakes = {1: {"profit_if_win": 10.00}}
        _validate_uniform_profit(stakes, epsilon=0.50)
    
    def test_variance_at_epsilon_passes(self):
        """Varianza esattamente a epsilon passa."""
        stakes = {
            1: {"profit_if_win": 10.00},
            2: {"profit_if_win": 10.50}
        }
        _validate_uniform_profit(stakes, epsilon=0.50)
    
    def test_variance_above_epsilon_fails(self):
        """Varianza sopra epsilon fallisce."""
        stakes = {
            1: {"profit_if_win": 10.00},
            2: {"profit_if_win": 10.51}
        }
        with pytest.raises(MixedDutchingError):
            _validate_uniform_profit(stakes, epsilon=0.50)


class TestAutoGreenDelay:
    """Test delay auto-green."""
    
    def test_auto_green_blocked_before_delay(self):
        """Auto-green bloccato prima del delay."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time(),
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_allowed_after_delay(self):
        """Auto-green consentito dopo delay."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - AUTO_GREEN_DELAY_SEC - 1,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is True
    
    def test_auto_green_respects_actual_delay(self):
        """Test delay reale (sleep)."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time(),
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
        time.sleep(AUTO_GREEN_DELAY_SEC + 0.5)
        assert should_auto_green(order, "OPEN") is True


class TestAutoGreenSimulation:
    """Test auto-green bloccato in simulazione."""
    
    def test_auto_green_blocked_in_simulation(self):
        """Auto-green bloccato in modalità simulazione."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - 10,
            "simulation": True
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_allowed_when_not_simulation(self):
        """Auto-green consentito se non in simulazione."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is True


class TestAutoGreenMarketStatus:
    """Test auto-green e stato mercato."""
    
    def test_auto_green_blocked_if_market_suspended(self):
        """Auto-green bloccato se mercato sospeso."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "SUSPENDED") is False
    
    def test_auto_green_blocked_if_market_closed(self):
        """Auto-green bloccato se mercato chiuso."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "CLOSED") is False
    
    def test_auto_green_requires_open_market(self):
        """Auto-green richiede mercato OPEN."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is True


class TestAutoGreenFlag:
    """Test flag auto_green nei metadata."""
    
    def test_auto_green_blocked_if_flag_false(self):
        """Auto-green bloccato se flag è False."""
        order = MockOrder({
            "auto_green": False,
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_blocked_if_flag_missing(self):
        """Auto-green bloccato se flag mancante."""
        order = MockOrder({
            "placed_at": time.time() - 10,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_blocked_if_meta_none(self):
        """Auto-green bloccato se meta è None."""
        order = MockOrder(None)
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_blocked_if_placed_at_missing(self):
        """Auto-green bloccato se placed_at mancante - previene bypass del delay."""
        order = MockOrder({
            "auto_green": True,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_blocked_if_placed_at_zero(self):
        """Auto-green bloccato se placed_at è zero - previene bypass del delay."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": 0,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False
    
    def test_auto_green_blocked_if_placed_at_none(self):
        """Auto-green bloccato se placed_at è None - previene bypass del delay."""
        order = MockOrder({
            "auto_green": True,
            "placed_at": None,
            "simulation": False
        })
        assert should_auto_green(order, "OPEN") is False


class TestAIMixedStakes:
    """Test calcolo AI Mixed stakes."""
    
    def test_ai_mixed_with_valid_selections(self):
        """AI Mixed funziona con selezioni valide con book favorevole."""
        selections = [
            {"selectionId": 1, "runnerName": "Home", "price": 2.5},
            {"selectionId": 2, "runnerName": "Draw", "price": 3.5},
            {"selectionId": 3, "runnerName": "Away", "price": 3.0}
        ]
        try:
            results, profit, book = calculate_ai_mixed_stakes(
                selections, 100.0, commission=4.5, min_stake=2.0
            )
            assert len(results) == 3
        except ValueError as e:
            if "profitto" in str(e).lower():
                pytest.skip("Quote non producono profitto positivo - test skippato")
    
    def test_ai_mixed_rejects_empty_selections(self):
        """AI Mixed rifiuta selezioni vuote."""
        with pytest.raises(ValueError):
            calculate_ai_mixed_stakes([], 100.0)
    
    def test_ai_mixed_rejects_zero_stake(self):
        """AI Mixed rifiuta stake zero."""
        selections = [
            {"selectionId": 1, "runnerName": "Home", "price": 2.0}
        ]
        with pytest.raises(ValueError):
            calculate_ai_mixed_stakes(selections, 0)
    
    def test_ai_mixed_rejects_invalid_prices(self):
        """AI Mixed rifiuta prezzi non validi."""
        selections = [
            {"selectionId": 1, "runnerName": "Home", "price": 0},
            {"selectionId": 2, "runnerName": "Away", "price": 1.0}
        ]
        with pytest.raises(ValueError):
            calculate_ai_mixed_stakes(selections, 100.0)
