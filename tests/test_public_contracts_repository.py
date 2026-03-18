import importlib
import sys
import types


def _install_betfair_stubs():
    if "betfairlightweight" in sys.modules:
        return

    mod = types.ModuleType("betfairlightweight")
    mod.APIClient = object
    mod.exceptions = types.SimpleNamespace(
        LoginError=Exception,
        CertsError=Exception,
        APIError=Exception,
    )
    filters_mod = types.SimpleNamespace(
        price_projection=lambda **kwargs: kwargs,
        market_filter=lambda **kwargs: kwargs,
        time_range=lambda **kwargs: kwargs,
    )

    streaming_mod = types.ModuleType("betfairlightweight.streaming")

    class StreamListener:
        pass

    streaming_mod.StreamListener = StreamListener
    mod.filters = filters_mod

    sys.modules["betfairlightweight"] = mod
    sys.modules["betfairlightweight.streaming"] = streaming_mod


_install_betfair_stubs()

PUBLIC_APIS = {
    "core.event_bus": ["EventBus"],
    "order_manager": ["OrderManager"],
    "executor_manager": ["SafeExecutor", "ExecutorManager"],
    "circuit_breaker": ["CircuitBreaker", "TransientError", "PermanentError"],
    "shutdown_manager": ["ShutdownManager"],
    "market_tracker": ["MarketCache", "DeltaDetector", "MarketTracker"],
    "tick_dispatcher": ["TickDispatcher", "TickData", "DispatchMode", "get_tick_dispatcher"],
    "tick_storage": ["TickStorage", "Tick", "OHLC"],
    "betfair_client": ["BetfairClient", "with_retry"],
    "telegram_sender": ["TelegramSender", "AdaptiveRateLimiter", "SendResult", "QueuedMessage"],
    "controllers.telegram_controller": ["TelegramController"],
    "pnl_engine": ["PnLEngine"],
    "repo_update_engine": ["process", "run_pytest", "create_file", "append_file"],
    "core.trading_engine": ["TradingEngine"],
}


def test_public_contracts_exist():
    for module_name, attrs in PUBLIC_APIS.items():
        mod = importlib.import_module(module_name)
        for attr in attrs:
            assert hasattr(mod, attr), f"{module_name} missing {attr}"


def test_public_contracts_are_runtime_objects_not_only_names():
    for module_name, attrs in PUBLIC_APIS.items():
        mod = importlib.import_module(module_name)
        for attr in attrs:
            obj = getattr(mod, attr)
            assert obj is not None, f"{module_name}.{attr} is None"


def test_public_contract_event_bus_runtime_behavior():
    mod = importlib.import_module("core.event_bus")
    bus = mod.EventBus()

    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("TEST_EVT", handler)
    bus.publish("TEST_EVT", {"value": 7})
    bus.unsubscribe("TEST_EVT", handler)
    bus.publish("TEST_EVT", {"value": 8})

    assert received == [{"value": 7}]


def test_public_contract_executor_manager_runtime_behavior():
    mod = importlib.import_module("executor_manager")

    with mod.ExecutorManager(max_workers=2, default_timeout=1) as manager:
        value = manager.submit("mul", lambda a, b: a * b, 3, 4)
        assert value == 12


def test_public_contract_market_tracker_runtime_behavior():
    mod = importlib.import_module("market_tracker")

    cache = mod.MarketCache(ttl=5.0, max_size=10)
    cache.set("1.123", {"status": "OPEN"})
    assert cache.get("1.123") == {"status": "OPEN"}

    detector = mod.DeltaDetector(min_price_change=0.01, min_volume_change=1.0)
    changed, reason = detector.has_changed(
        market_id="1.123",
        selection_id=1,
        back_price=2.0,
        lay_price=2.02,
        back_size=100,
        lay_size=100,
    )

    assert changed is True
    assert isinstance(reason, str)
    assert reason


def test_public_contract_tick_dispatcher_runtime_behavior():
    mod = importlib.import_module("tick_dispatcher")

    dispatcher = mod.TickDispatcher()
    received = []

    dispatcher.register_storage_callback(lambda tick: received.append(tick.market_id))

    tick = mod.TickData(
        market_id="1.555",
        selection_id=99,
        timestamp=123.0,
        back_prices=[1.9],
        lay_prices=[2.0],
    )
    dispatcher.dispatch_tick(tick)

    assert received == ["1.555"]


def test_public_contract_pnl_engine_runtime_behavior():
    mod = importlib.import_module("pnl_engine")
    engine = mod.PnLEngine(commission=4.5)

    order = {
        "side": "BACK",
        "stake": 10.0,
        "price": 2.0,
    }

    pnl = engine.calculate_order_pnl(order, best_back=1.95, best_lay=1.80)

    assert isinstance(pnl, float)
    assert pnl != 0.0


def test_public_contract_repo_update_engine_runtime_behavior(tmp_path):
    mod = importlib.import_module("repo_update_engine")

    target = tmp_path / "repo_contract.txt"
    mod.create_file(str(target), "one")
    mod.append_file(str(target), "\ntwo")

    content = target.read_text(encoding="utf-8")
    assert content == "one\ntwo"