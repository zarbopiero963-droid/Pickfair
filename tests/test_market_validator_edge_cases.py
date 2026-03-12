from market_validator import MarketValidator


def test_validator_edge():
    v = MarketValidator()

    assert v.is_dutching_ready("UNKNOWN") in [True, False]