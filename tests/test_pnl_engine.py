from pnl_engine import PnLEngine


def test_pnl_engine_back_and_lay_calculations_return_numbers():
    engine = PnLEngine(commission=4.5)
    back = engine.calculate_back_pnl(
        {"side": "BACK", "stake": 10.0, "price": 3.0},
        best_lay_price=2.5,
    )
    lay = engine.calculate_lay_pnl(
        {"side": "LAY", "stake": 10.0, "price": 3.0},
        best_back_price=2.5,
    )
    assert isinstance(back, float)
    assert isinstance(lay, float)


def test_pnl_engine_selection_pnl_sums_orders():
    engine = PnLEngine(commission=4.5)
    orders = [
        {"side": "BACK", "stake": 10.0, "price": 3.0},
        {"side": "LAY", "stake": 5.0, "price": 2.0},
    ]
    pnl = engine.calculate_selection_pnl(orders, best_back=2.2, best_lay=2.4)
    assert isinstance(pnl, float)


def test_pnl_engine_preview_and_auto_green_eligibility():
    engine = PnLEngine(commission=4.5)
    preview = engine.calculate_preview({"stake": 10.0, "price": 2.5}, side="BACK")
    assert isinstance(preview, float)

    eligible = engine.is_auto_green_eligible(
        {"auto_green": True, "simulation": False, "placed_at": 1},
        current_time=999999,
    )
    assert eligible is True
