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
    "executor_manager": ["SafeExecutor"],
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
