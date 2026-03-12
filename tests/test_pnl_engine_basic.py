from pnl_engine import PnLEngine


def test_pnl_calculation_back_win():
    engine = PnLEngine()

    pnl = engine.calculate_back_profit(
        stake=10,
        price=2.0,
    )

    assert pnl == 10


def test_pnl_calculation_back_loss():
    engine = PnLEngine()

    pnl = engine.calculate_back_loss(stake=10)

    assert pnl == -10