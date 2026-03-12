from controllers.dutching_controller import DutchingController


def test_liquidity_guard_shape():
    ctrl = DutchingController()

    ok, msgs = ctrl._check_liquidity_guard([], "BACK", "1.123")

    assert isinstance(ok, bool)
    assert isinstance(msgs, list)