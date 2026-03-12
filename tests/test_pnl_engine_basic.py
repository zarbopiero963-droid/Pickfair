from pnl_engine import PnLEngine


def test_pnl_basic():
    pnl = PnLEngine()

    result = pnl.calculate_profit(100, 110)

    assert result >= 0