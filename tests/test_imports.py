import sys
import time
import types

import pytest


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

from betfair_client import with_retry
from circuit_breaker import CircuitBreaker, PermanentError, TransientError
from executor_manager import SafeExecutor
from market_tracker import DeltaDetector, MarketCache
from tick_dispatcher import DispatchMode, TickData, TickDispatcher, get_tick_dispatcher
from trading_config import MIN_LIQUIDITY, MIN_STAKE


def test_trading_config_runtime_constants_are_valid():
    assert isinstance(MIN_STAKE, (int, float))
    assert isinstance(MIN_LIQUIDITY, (int, float))
    assert MIN_STAKE > 0
    assert MIN_LIQUIDITY > 0


def test_market_cache_set_get_and_stats_are_real():
    cache = MarketCache(ttl=10.0, max_size=2)

    data = {"marketId": "1.123", "status": "OPEN"}
    cache.set("1.123", data)

    first = cache.get("1.123")
    second = cache.get("missing")

    assert first == data
    assert second is None

    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["cache_size"] == 1
    assert stats["api_calls_saved"] == 1


def test_market_cache_eviction_respects_max_size():
    cache = MarketCache(ttl=10.0, max_size=2)

    cache.set("1", {"v": 1})
    cache.set("2", {"v": 2})
    cache.set("3", {"v": 3})

    remaining = {
        market_id
        for market_id in ["1", "2", "3"]
        if cache.get(market_id) is not None
    }

    assert len(remaining) == 2
    assert "3" in remaining


def test_delta_detector_skips_small_changes_and_detects_real_ones():
    detector = DeltaDetector(min_price_change=0.02, min_volume_change=5.0)

    changed_1, reason_1 = detector.has_changed(
        market_id="1.123",
        selection_id=10,
        back_price=2.00,
        lay_price=2.02,
        back_size=100,
        lay_size=100,
    )
    assert changed_1 is True
    assert "Prima lettura" in reason_1

    changed_2, reason_2 = detector.has_changed(
        market_id="1.123",
        selection_id=10,
        back_price=2.01,
        lay_price=2.03,
        back_size=102,
        lay_size=103,
    )
    assert changed_2 is False
    assert "Nessun cambiamento significativo" in reason_2

    changed_3, reason_3 = detector.has_changed(
        market_id="1.123",
        selection_id=10,
        back_price=2.05,
        lay_price=2.08,
        back_size=120,
        lay_size=130,
    )
    assert changed_3 is True
    assert ("Prezzo" in reason_3) or ("Volume" in reason_3)


def test_safe_executor_returns_result_for_fast_callable():
    executor = SafeExecutor(max_workers=2, default_timeout=1)

    result = executor.submit("sum", lambda a, b: a + b, 2, 3)

    assert result == 5
    executor.executor.shutdown(wait=False)


def test_safe_executor_raises_timeout_for_slow_callable():
    executor = SafeExecutor(max_workers=2, default_timeout=0.01)

    with pytest.raises(Exception):
        executor.submit("slow", lambda: time.sleep(0.05))

    executor.executor.shutdown(wait=False)


def test_circuit_breaker_marks_transient_and_opens_after_limit():
    breaker = CircuitBreaker(max_failures=2, reset_timeout=30)

    def flaky():
        raise RuntimeError("network timeout")

    with pytest.raises(TransientError):
        breaker.call(flaky)

    with pytest.raises(TransientError):
        breaker.call(flaky)

    assert breaker.is_open() is True

    with pytest.raises(RuntimeError, match="Circuit breaker OPEN"):
        breaker.call(flaky)


def test_circuit_breaker_raises_permanent_error_without_retry_state_growth():
    breaker = CircuitBreaker(max_failures=3, reset_timeout=30)

    def permanent():
        raise RuntimeError("insufficient_funds")

    with pytest.raises(PermanentError):
        breaker.call(permanent)

    assert breaker.failures == 0
    assert breaker.is_open() is False


def test_with_retry_retries_network_errors_and_returns_on_success(monkeypatch):
    calls = {"count": 0}

    monkeypatch.setattr("betfair_client.time.sleep", lambda *_: None)

    @with_retry
    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("502 bad gateway")
        return "ok"

    assert flaky() == "ok"
    assert calls["count"] == 3


def test_tick_dispatcher_dispatches_storage_and_ui_callbacks():
    dispatcher = TickDispatcher()

    storage_calls = []
    ui_calls = []

    dispatcher.register_storage_callback(lambda tick: storage_calls.append(tick.market_id))
    dispatcher.register_ui_callback(lambda ticks: ui_calls.append(sorted(ticks.keys())))

    tick = TickData(
        market_id="1.123",
        selection_id=10,
        timestamp=time.time(),
        back_prices=[2.0],
        lay_prices=[2.02],
    )

    dispatcher.dispatch_tick(tick)

    assert storage_calls == ["1.123"]
    assert ui_calls == [["1.123"]]

    stats = dispatcher.get_stats()
    assert stats["total_ticks"] == 1
    assert stats["ui_dispatches"] == 1


def test_tick_dispatcher_mode_changes_runtime_intervals():
    dispatcher = TickDispatcher()

    assert dispatcher.mode == DispatchMode.LIVE
    assert dispatcher.ui_interval == dispatcher.MIN_UI_UPDATE_INTERVAL
    assert dispatcher.automation_interval == dispatcher.MIN_AUTOMATION_INTERVAL

    dispatcher.mode = DispatchMode.SIMULATION

    assert dispatcher.ui_interval == dispatcher.SIM_UI_UPDATE_INTERVAL
    assert dispatcher.automation_interval == dispatcher.SIM_AUTOMATION_INTERVAL


def test_get_tick_dispatcher_returns_singleton_instance():
    d1 = get_tick_dispatcher()
    d2 = get_tick_dispatcher()

    assert d1 is d2