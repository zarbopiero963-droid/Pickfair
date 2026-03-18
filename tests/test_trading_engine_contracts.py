from core.trading_engine import TradingEngine


class DummyBus:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, event_name, handler):
        self.subscribers.setdefault(event_name, []).append(handler)

    def publish(self, event_name, payload):
        for handler in self.subscribers.get(event_name, []):
            handler(payload)


class DummyDB:
    pass


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def build_engine():
    return TradingEngine(
        bus=DummyBus(),
        db=DummyDB(),
        client_getter=lambda: None,
        executor=DummyExecutor(),
    )


def test_trading_engine_subscribes_core_commands_on_init():
    engine = build_engine()

    assert "CMD_QUICK_BET" in engine.bus.subscribers
    assert "CMD_PLACE_DUTCHING" in engine.bus.subscribers
    assert "CMD_EXECUTE_CASHOUT" in engine.bus.subscribers
    assert "STATE_UPDATE_SAFE_MODE" in engine.bus.subscribers
    assert "CLIENT_CONNECTED" in engine.bus.subscribers


def test_trading_engine_toggle_kill_switch_accepts_dict_and_bool():
    engine = build_engine()

    engine._toggle_kill_switch({"enabled": True})
    assert engine.is_killed is True

    engine._toggle_kill_switch(False)
    assert engine.is_killed is False


def test_trading_engine_compute_order_status_real_cases():
    engine = build_engine()

    assert engine._compute_order_status(0, 10) == "UNMATCHED"
    assert engine._compute_order_status(10, 10) == "MATCHED"
    assert engine._compute_order_status(9.995, 10) == "MATCHED"
    assert engine._compute_order_status(4, 10) == "PARTIALLY_MATCHED"


def test_trading_engine_detects_micro_stake_range_correctly():
    engine = build_engine()

    assert engine._needs_micro_stake(0.05) is False
    assert engine._needs_micro_stake(0.10) is True
    assert engine._needs_micro_stake(1.99) is True
    assert engine._needs_micro_stake(2.00) is False


def test_trading_engine_micro_stub_prices_depend_on_side():
    engine = build_engine()

    assert engine._micro_stub_price("BACK") == 1.01
    assert engine._micro_stub_price("LAY") == 1000.0


def test_trading_engine_lock_prevents_duplicate_customer_ref():
    engine = build_engine()

    assert engine._acquire_lock("REF-1") is True
    assert engine._acquire_lock("REF-1") is False

    engine._release_lock("REF-1")

    assert engine._acquire_lock("REF-1") is True


def test_trading_engine_detects_stub_micro_orders():
    engine = build_engine()

    assert engine._is_stub_micro_order(
        {"price": 1.01, "sizeRemaining": 1.0}
    ) is True
    assert engine._is_stub_micro_order(
        {"price": 1000.0, "sizeRemaining": 0.5}
    ) is True
    assert engine._is_stub_micro_order(
        {"price": 2.0, "sizeRemaining": 1.0}
    ) is False
    assert engine._is_stub_micro_order(
        {"price": 1.01, "sizeRemaining": 0.0}
    ) is False 