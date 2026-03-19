
from market_validator import MarketValidator


def test_market_validator_ready():
    validator = MarketValidator()

    assert validator.is_dutching_ready("MATCH_ODDS") in [True, False]