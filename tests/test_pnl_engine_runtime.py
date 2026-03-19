from pnl_engine import PnLEngine


def test_back_profit_calculation():
    pnl = PnLEngine()

    result = pnl.calculate_profit(
        stake=10,
        odds=2.0,
        side="BACK",
    )

    assert result == 10


def test_lay_profit_calculation():
    pnl = PnLEngine()

    result = pnl.calculate_profit(
        stake=10,
        odds=2.0,
        side="LAY",
    )

    assert result == 10


def test_zero_profit_when_odds_equal_one():
    pnl = PnLEngine()

    result = pnl.calculate_profit(
        stake=10,
        odds=1.0,
        side="BACK",
    )

    assert result == 0


def test_invalid_side_raises_error():
    pnl = PnLEngine()

    try:
        pnl.calculate_profit(
            stake=10,
            odds=2.0,
            side="INVALID",
        )
        raise AssertionError()
    except Exception:
        assert True