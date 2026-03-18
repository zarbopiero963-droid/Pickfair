import importlib
import sys
import tempfile
import types
from pathlib import Path


def _install_betfair_stubs():
    if "betfairlightweight" not in sys.modules:
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

    if "telethon" not in sys.modules:
        telethon_mod = types.ModuleType("telethon")
        telethon_mod.TelegramClient = object
        telethon_mod.events = object()

        sessions_mod = types.ModuleType("telethon.sessions")

        class DummyStringSession:
            def __init__(self, *args, **kwargs):
                pass

        sessions_mod.StringSession = DummyStringSession

        sys.modules["telethon"] = telethon_mod
        sys.modules["telethon.sessions"] = sessions_mod


_install_betfair_stubs()


def test_telegram_listener_public_api_and_real_parser_contract():
    mod = importlib.import_module("telegram_listener")

    assert hasattr(mod, "TelegramListener")
    assert hasattr(mod, "SignalQueue")
    assert hasattr(mod, "parse_signal_message")

    res = mod.parse_signal_message("CASHOUT ALL market_id=1.999")

    assert res is not None
    assert res["market_type"] == "CASHOUT"
    assert res["cashout_type"] == "ALL"


def test_event_bus_public_api_is_runtime_usable():
    mod = importlib.import_module("core.event_bus")
    bus = mod.EventBus()

    received = []
    bus.subscribe("PING", lambda payload: received.append(payload))
    bus.publish("PING", {"ok": True})

    assert received == [{"ok": True}]


def test_order_manager_public_api_exposes_real_compatibility_behavior():
    mod = importlib.import_module("order_manager")
    mgr = mod.OrderManager(app=None, bus=None, db=None)

    assert mgr.cancel_order("1.1", "BET1") is False
    assert mgr.replace_order("1.1", "BET1", 2.0) is False

    mgr.remember("x", {"value": 1})
    assert mgr.get_cached("x") == {"value": 1}

    status = mgr.get_status()
    assert status["cancel_supported"] is False
    assert status["replace_supported"] is False
    assert status["mode"] == "compatibility_layer_only"


def test_executor_manager_public_api_runs_and_shuts_down():
    mod = importlib.import_module("executor_manager")

    manager = mod.ExecutorManager(max_workers=2, default_timeout=1)
    result = manager.submit("sum", lambda a, b: a + b, 4, 5)

    assert result == 9
    assert manager.running is True

    manager.shutdown(wait=False)
    assert manager.running is False


def test_circuit_breaker_public_api_exports_expected_classes():
    mod = importlib.import_module("circuit_breaker")

    assert hasattr(mod, "CircuitBreaker")
    assert hasattr(mod, "TransientError")
    assert hasattr(mod, "PermanentError")

    breaker = mod.CircuitBreaker(max_failures=1, reset_timeout=10)

    def fail():
        raise RuntimeError("network timeout")

    try:
        breaker.call(fail)
    except mod.TransientError:
        pass

    assert breaker.is_open() is True


def test_shutdown_manager_public_api_executes_handlers_in_priority_order():
    mod = importlib.import_module("shutdown_manager")
    mgr = mod.ShutdownManager()

    calls = []

    mgr.register("late", lambda: calls.append("late"), priority=20)
    mgr.register("early", lambda: calls.append("early"), priority=5)

    mgr.shutdown()

    assert calls == ["early", "late"]


def test_market_tracker_public_api_cache_and_delta_work():
    mod = importlib.import_module("market_tracker")

    cache = mod.MarketCache(ttl=5.0, max_size=10)
    cache.set("1.123", {"status": "OPEN"})
    assert cache.get("1.123") == {"status": "OPEN"}

    detector = mod.DeltaDetector(min_price_change=0.01, min_volume_change=1.0)
    changed, _ = detector.has_changed("1.123", 10, 2.0, 2.02, 100, 100)
    assert changed is True


def test_tick_dispatcher_public_api_dispatches_tick():
    mod = importlib.import_module("tick_dispatcher")

    dispatcher = mod.TickDispatcher()
    storage = []

    dispatcher.register_storage_callback(lambda tick: storage.append(tick.selection_id))

    tick = mod.TickData(
        market_id="1.123",
        selection_id=77,
        timestamp=1.0,
        back_prices=[2.0],
        lay_prices=[2.02],
    )
    dispatcher.dispatch_tick(tick)

    assert storage == [77]
    assert mod.get_tick_dispatcher() is mod.get_tick_dispatcher()


def test_tick_storage_public_api_types_exist():
    mod = importlib.import_module("tick_storage")

    assert hasattr(mod, "Tick")
    assert hasattr(mod, "OHLC")
    assert hasattr(mod, "TickStorage")


def test_betfair_client_public_api_exports_retry_decorator():
    mod = importlib.import_module("betfair_client")
    assert hasattr(mod, "BetfairClient")
    assert hasattr(mod, "with_retry")


def test_telegram_sender_public_api_has_real_rate_limiter_contract():
    mod = importlib.import_module("telegram_sender")

    limiter = mod.AdaptiveRateLimiter(base_delay=0.5)
    assert limiter.get_stats()["current_delay"] == 0.5

    limiter.record_failure()
    assert limiter.get_stats()["current_delay"] >= 0.5

    limiter.record_flood_wait(30)
    assert limiter.get_stats()["current_delay"] >= 3.0

    result = mod.SendResult(success=True, message_id=123, error=None)
    assert result.success is True
    assert result.message_id == 123

    queued = mod.QueuedMessage(chat_id="1", text="hello", max_retries=2)
    assert queued.chat_id == "1"
    assert queued.text == "hello"
    assert queued.max_retries == 2


def test_telegram_controller_public_api_db_helpers_work():
    mod = importlib.import_module("controllers.telegram_controller")

    class DummyDB:
        def __init__(self):
            self.saved = None

        def get_telegram_settings(self):
            return {"api_id": "1"}

        def save_telegram_settings(self, data):
            self.saved = data

    class DummyApp:
        def __init__(self):
            self.db = DummyDB()

    controller = mod.TelegramController(DummyApp())

    assert controller._get_settings()["api_id"] == "1"
    controller._save_settings_dict({"api_id": "2"})
    assert controller.app.db.saved == {"api_id": "2"}


def test_pnl_engine_public_api_returns_preview_values():
    mod = importlib.import_module("pnl_engine")
    engine = mod.PnLEngine(commission=4.5)

    back_preview = engine.calculate_preview({"stake": 10.0, "price": 2.0}, side="BACK")
    lay_preview = engine.calculate_preview({"stake": 10.0, "price": 2.0}, side="LAY")

    assert isinstance(back_preview, float)
    assert isinstance(lay_preview, float)
    assert back_preview > 0


def test_repo_update_engine_public_api_file_ops_work(tmp_path):
    mod = importlib.import_module("repo_update_engine")

    target = tmp_path / "sample.txt"
    mod.create_file(str(target), "alpha")
    mod.append_file(str(target), "\nbeta")

    content = target.read_text(encoding="utf-8")
    assert "alpha" in content
    assert "beta" in content
    assert callable(mod.run_pytest)
    assert callable(mod.process)