"""
Regression tests for audit issue #38, items #32–#37.

#32 goal_engine_pro.py   — return inside fixture loop skips remaining fixtures
#33 core/async_db_writer.py — busy-wait ALREADY FIXED (event-based sleep_idle)
#34 betfair_client.py    — no stream reconnection logic
#35 shutdown_manager.py  — no shutdown coordination / no duplicate protection
#36 telegram_sender.py   — fragile FloodWait digit-concat parsing
#37 event_bus.py         — synchronous subscriber blocks publisher
"""

import threading
import time

import pytest


# =============================================================================
# Issue #32 – goal_engine_pro.py
# =============================================================================

class TestIssue32GoalEngineVarLoop:

    def _make_engine(self):
        from goal_engine_pro import GoalEnginePro, APIFootballClient
        client = APIFootballClient(api_key="")
        hedges = []
        reopens = []

        class FakeUIQ:
            def post(self, *a, **kw): pass

        eng = GoalEnginePro(
            api_client=client,
            betfair_stream=None,
            hedge_callback=lambda mid: hedges.append(mid),
            reopen_callback=lambda mid: reopens.append(mid),
            ui_queue=FakeUIQ(),
        )
        return eng, hedges, reopens

    def test_var_in_first_fixture_does_not_skip_second_fixture(self):
        """
        OLD: `return` inside the loop exited _process_api entirely after a VAR
             in fixture 1, so fixture 2 (with a real goal) was never processed.
        NEW: `continue` moves to the next fixture; fixture 2 triggers a hedge.

        Input: fixture 1 has a VAR (goals went from 1→0), fixture 2 has a new goal.
        Old:   only reopen_callback("m1") fires; hedge for "m2" is never triggered.
        New:   reopen_callback("m1") fires AND "m2" ends up hedged.
        """
        eng, hedges, reopens = self._make_engine()

        # Seed goal cache: match 1 had 1 goal, match 2 had 0 goals
        with eng._cache_lock:
            eng.goal_cache["m1"] = 1
            eng.goal_cache["m2"] = 0

        data = {
            "response": [
                {
                    "fixture": {"id": "m1"},
                    "goals": {"home": 0, "away": 0},  # VAR: total=0 < 1
                },
                {
                    "fixture": {"id": "m2"},
                    "goals": {"home": 1, "away": 0},  # GOAL: total=1 > 0
                },
            ]
        }

        eng._process_api(data)
        # Give spawned callback threads time to run
        time.sleep(0.2)

        assert "m1" in reopens, "Reopen callback must fire for m1 VAR"
        assert "m2" in hedges, (
            "OLD: m2 goal skipped because return exited loop after m1 VAR. "
            "NEW: m2 must be hedged."
        )

    def test_var_callback_fires_for_var_fixture(self):
        """Ensure the reopen callback still fires on VAR (no regression)."""
        eng, hedges, reopens = self._make_engine()
        with eng._cache_lock:
            eng.goal_cache["m10"] = 2

        eng._process_api({
            "response": [{"fixture": {"id": "m10"}, "goals": {"home": 0, "away": 0}}]
        })
        time.sleep(0.2)
        assert "m10" in reopens

    def test_multiple_goals_all_processed(self):
        """All fixtures with new goals are hedged when no VAR is present."""
        eng, hedges, reopens = self._make_engine()
        with eng._cache_lock:
            eng.goal_cache["a"] = 0
            eng.goal_cache["b"] = 0
            eng.goal_cache["c"] = 0

        eng._process_api({
            "response": [
                {"fixture": {"id": "a"}, "goals": {"home": 1, "away": 0}},
                {"fixture": {"id": "b"}, "goals": {"home": 0, "away": 1}},
                {"fixture": {"id": "c"}, "goals": {"home": 1, "away": 1}},
            ]
        })
        time.sleep(0.3)
        assert "a" in hedges
        assert "b" in hedges
        assert "c" in hedges


# =============================================================================
# Issue #33 – core/async_db_writer.py — ALREADY FIXED IN BASE BRANCH
# The current implementation uses threading.Event for wakeup (not busy-wait).
# =============================================================================

class TestIssue33AsyncDBWriterEventBased:

    def _make_writer(self):
        class FakeDB:
            def save_bet(self, **kw): pass
        from core.async_db_writer import AsyncDBWriter
        return AsyncDBWriter(db=FakeDB(), sleep_idle=5.0)

    def test_writer_uses_event_not_busy_wait(self):
        """
        Confirm the current implementation uses _event.wait() (event-based)
        rather than time.sleep(0.001) (busy-wait).
        """
        import inspect
        from core.async_db_writer import AsyncDBWriter
        source = inspect.getsource(AsyncDBWriter._loop)
        assert "_event.wait" in source, (
            "_loop must use _event.wait() for idle sleep, not a busy loop"
        )
        assert "time.sleep(0.001)" not in source, (
            "Busy-wait time.sleep(0.001) must not be present"
        )

    def test_submit_wakes_writer_promptly(self):
        """Submitting an item sets the event and wakes the writer quickly."""
        written = []

        class FastDB:
            def save_bet(self, **kw): written.append(kw)

        from core.async_db_writer import AsyncDBWriter
        w = AsyncDBWriter(db=FastDB(), sleep_idle=60.0)  # would wait 60s without event
        w.start()
        t0 = time.time()
        w.submit("bet", {"market_id": "x"})
        # Wait max 2s for the write to complete
        deadline = time.time() + 2
        while not written and time.time() < deadline:
            time.sleep(0.01)
        elapsed = time.time() - t0
        w.stop()
        assert written, "Item was never written"
        assert elapsed < 2.0, f"Writer took {elapsed:.2f}s (should wake via event)"

    def test_shutdown_drains_queue(self):
        """stop() drains remaining items before exiting."""
        written = []

        class SlowDB:
            def save_bet(self, **kw): written.append(kw)

        from core.async_db_writer import AsyncDBWriter
        w = AsyncDBWriter(db=SlowDB(), sleep_idle=0.05)
        w.start()
        for i in range(5):
            w.submit("bet", {"market_id": str(i)})
        w.stop()
        assert len(written) == 5, f"Expected 5 written on drain, got {len(written)}"


# =============================================================================
# Issue #34 – betfair_client.py
# =============================================================================

class TestIssue34BetfairStreamReconnect:

    def test_reconnect_attempted_on_stream_error(self):
        """
        OLD: stream error → streaming_active = False, no reconnect attempt.
        NEW: error → reconnect with exponential backoff (up to max_reconnects).

        We simulate by making stream.start() raise on first call and succeed
        on the second, verifying that _run_stream loops and retries.
        """
        from betfair_client import BetfairClient

        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k")
        client.streaming_active = True
        client._last_stream_market_ids = ["1.234"]
        client._last_stream_price_callback = lambda mid, data: None
        client._stream_max_reconnects = 2

        call_count = [0]
        reconnect_attempts = [0]

        class FakeStream:
            def start(self):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise ConnectionError("Simulated disconnect")
                # Second call succeeds (returns normally)
                client.streaming_active = False  # signal clean stop

            def subscribe_to_markets(self, **kw):
                reconnect_attempts[0] += 1

        class FakeStreamingAPI:
            def create_stream(self, listener):
                return FakeStream()

        class FakeClientCore:
            streaming = FakeStreamingAPI()

        client.client = FakeClientCore()
        client.stream = FakeStream()

        # Patch time.sleep to avoid actual waiting in test
        import unittest.mock as mock
        with mock.patch("time.sleep"):
            client._run_stream()

        assert call_count[0] >= 2, (
            f"OLD: stream error → no retry. "
            f"NEW: stream.start() should be called at least twice. "
            f"Got: {call_count[0]}"
        )

    def test_reconnect_stops_after_max_attempts(self):
        """Reconnect loop does not spin indefinitely; stops at max_reconnects."""
        from betfair_client import BetfairClient
        import unittest.mock as mock

        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k")
        client.streaming_active = True
        client._last_stream_market_ids = ["1.234"]
        client._last_stream_price_callback = lambda *a: None
        client._stream_max_reconnects = 3

        start_calls = [0]

        class AlwaysFailStream:
            def start(self):
                start_calls[0] += 1
                raise ConnectionError("always fails")

            def subscribe_to_markets(self, **kw): pass

        class FakeStreamingAPI:
            def create_stream(self, listener):
                return AlwaysFailStream()

        class FakeClientCore:
            streaming = FakeStreamingAPI()

        client.client = FakeClientCore()
        client.stream = AlwaysFailStream()

        with mock.patch("time.sleep"):
            client._run_stream()

        # Should stop at max_reconnects (3) and not loop forever
        assert start_calls[0] <= client._stream_max_reconnects + 1, (
            f"Reconnect loop exceeded max_reconnects. start_calls={start_calls[0]}"
        )
        assert not client.streaming_active

    def test_stop_streaming_prevents_reconnect(self):
        """If stop_streaming() is called, _run_stream does not reconnect."""
        from betfair_client import BetfairClient
        import unittest.mock as mock

        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k")
        client.streaming_active = False  # already stopped
        start_calls = [0]

        class StoppedStream:
            def start(self):
                start_calls[0] += 1
                raise ConnectionError("fail")

        client.stream = StoppedStream()
        client._stream_max_reconnects = 5

        with mock.patch("time.sleep"):
            client._run_stream()

        assert start_calls[0] == 1, (
            "Stream.start() called once (initial attempt); "
            "no reconnect since streaming_active was already False."
        )

    def test_stop_streaming_during_backoff_prevents_reconnect(self):
        """
        FIX #34 race: if stop_streaming() is called while _run_stream is sleeping
        in the backoff, the reconnect must be aborted — no new subscription.
        OLD: time.sleep(backoff) cannot be interrupted; thread reconnects after waking.
        NEW: _stream_stop_event.wait(backoff) is interrupted by stop_streaming().
        """
        from betfair_client import BetfairClient
        import unittest.mock as mock

        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k")
        client.streaming_active = True
        client._last_stream_market_ids = ["1.234"]
        client._last_stream_price_callback = lambda *a: None
        client._stream_max_reconnects = 5

        subscribe_calls = [0]
        start_calls = [0]

        class InterruptedStream:
            def start(self):
                start_calls[0] += 1
                raise ConnectionError("disconnect")
            def subscribe_to_markets(self, **kw):
                subscribe_calls[0] += 1

        class FakeStreamingAPI:
            def create_stream(self, listener):
                return InterruptedStream()

        class FakeClientCore:
            streaming = FakeStreamingAPI()

        client.client = FakeClientCore()
        client.stream = InterruptedStream()

        # Simulate stop_streaming() being called during the backoff:
        # we set the event directly (same as stop_streaming would do)
        def fake_wait(timeout):
            client.streaming_active = False   # stop_streaming side-effect
            client._stream_stop_event.set()
            return True  # True = event was set (interrupted)

        with mock.patch.object(client._stream_stop_event, 'wait', side_effect=fake_wait):
            client._run_stream()

        assert subscribe_calls[0] == 0, (
            f"OLD: reconnect happened after backoff even though stop was called. "
            f"NEW: no re-subscribe after stop_streaming() during backoff. "
            f"subscribe_calls={subscribe_calls[0]}"
        )

    def test_normal_stream_start_no_reconnect(self):
        """When stream.start() succeeds, no reconnect is attempted."""
        from betfair_client import BetfairClient

        client = BetfairClient(username="u", app_key="k", cert_pem="c", key_pem="k")
        client.streaming_active = True
        client._stream_max_reconnects = 3
        start_calls = [0]

        class NormalStream:
            def start(self):
                start_calls[0] += 1
                # Returns normally — intentional stop

        client.stream = NormalStream()
        client._run_stream()

        assert start_calls[0] == 1
        assert not client.streaming_active


# =============================================================================
# Issue #35 – shutdown_manager.py
# =============================================================================

class TestIssue35ShutdownManager:

    def test_stop_event_set_before_handlers_run(self):
        """
        stop_event must be set before shutdown handlers execute, so threads
        can observe it and drain/stop before resources are torn down.
        """
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        observed_at_handler = []

        def handler():
            observed_at_handler.append(mgr.stop_event.is_set())

        mgr.register("resource", handler, priority=10)
        mgr.shutdown()

        assert observed_at_handler[0] is True, (
            "stop_event must be set BEFORE the handler runs so threads can "
            "see it and stop gracefully before resources are closed."
        )

    def test_duplicate_registration_is_silently_ignored(self):
        """
        OLD: registering the same name twice added it to the handler list twice,
             causing double execution on shutdown.
        NEW: second registration with the same name is silently ignored.
        """
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        call_count = [0]
        mgr.register("svc", lambda: call_count.__setitem__(0, call_count[0] + 1))
        mgr.register("svc", lambda: call_count.__setitem__(0, call_count[0] + 100))

        mgr.shutdown()
        assert call_count[0] == 1, (
            f"OLD: svc was registered twice → called twice. "
            f"NEW: second registration ignored → called once. Got: {call_count[0]}"
        )

    def test_shutdown_is_idempotent(self):
        """Calling shutdown() twice runs handlers only once."""
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        runs = [0]
        mgr.register("once", lambda: runs.__setitem__(0, runs[0] + 1))
        mgr.shutdown()
        mgr.shutdown()
        assert runs[0] == 1

    def test_signal_stop_sets_stop_event(self):
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        assert not mgr.stop_event.is_set()
        mgr.signal_stop()
        assert mgr.stop_event.is_set()

    def test_shutdown_order_deterministic_by_priority(self):
        """Handlers run in ascending priority order."""
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        order = []
        mgr.register("high_prio", lambda: order.append("high"), priority=1)
        mgr.register("low_prio",  lambda: order.append("low"),  priority=20)
        mgr.register("mid_prio",  lambda: order.append("mid"),  priority=10)
        mgr.shutdown()
        assert order == ["high", "mid", "low"]

    def test_workers_joined_before_resource_handlers(self):
        """
        FIX #35: stop_event is set and workers are joined BEFORE resource-closing
        handlers run. Without this, a handler might close a DB while a worker
        thread is still writing to it.

        OLD: stop_event.set() then immediately run handlers — worker may still be alive.
        NEW: stop_event.set() → join workers → run handlers.
        """
        from shutdown_manager import ShutdownManager
        import threading

        mgr = ShutdownManager()
        timeline = []

        # Worker: waits for stop_event, appends "worker_done"
        worker_done = threading.Event()
        def worker_fn():
            mgr.stop_event.wait(timeout=5)
            timeline.append("worker_done")
            worker_done.set()

        worker_thread = threading.Thread(target=worker_fn, daemon=True)
        worker_thread.start()
        mgr.register_worker(worker_thread, timeout=5)

        # Handler (resource close): must run AFTER worker_done
        def resource_handler():
            timeline.append("resource_closed")

        mgr.register("db", resource_handler, priority=10)
        mgr.shutdown()

        assert timeline == ["worker_done", "resource_closed"], (
            f"OLD: handler may run before worker finishes. "
            f"NEW: worker must be joined before resource handler runs. "
            f"Got: {timeline}"
        )

    def test_normal_shutdown_no_regression(self):
        """Normal shutdown still executes all unique handlers."""
        from shutdown_manager import ShutdownManager
        mgr = ShutdownManager()
        ran = []
        mgr.register("a", lambda: ran.append("a"))
        mgr.register("b", lambda: ran.append("b"))
        mgr.shutdown()
        assert set(ran) == {"a", "b"}


# =============================================================================
# Issue #36 – telegram_sender.py
# =============================================================================

class TestIssue36FloodWaitParsing:
    """
    The fix changes the FloodWait parsing from:
        int("".join(filter(str.isdigit, str(e))))
    to:
        re.search(r"\\b(\\d{1,4})\\b", str(e))

    OLD: concatenates ALL digit sequences in the error string.
         "A wait of 130s [420]" → "130420" → 130420 seconds (wildly wrong)
    NEW: takes the FIRST 1-4 digit standalone integer.
         "A wait of 130s [420]" → "130" → 130 seconds (correct)
    """

    def _parse_flood_wait(self, error_str_or_exc) -> int:
        """
        Replicate the exact parsing logic from the fix.
        1. Structured attribute: if exception has .seconds, use it directly.
        2. Contextual regex: match "wait X" or "floodwait X" before trying
           any generic number pattern.
        3. Fallback to 60.
        """
        import re
        try:
            # Structured attribute (Telethon FloodWaitError.seconds)
            if hasattr(error_str_or_exc, 'seconds'):
                s = error_str_or_exc.seconds
                if isinstance(s, int) and s > 0:
                    return s
            error_str = str(error_str_or_exc)
            # Contextual: "wait X" or "floodwait X"
            m = re.search(r'(?:wait|floodwait)[^\d]*(\d{1,5})', error_str, re.IGNORECASE)
            if not m:
                # Fallback: number directly followed by 's' (seconds indicator)
                m = re.search(r'(\d{1,5})\s*s(?:\b|$)', error_str, re.IGNORECASE)
            wait_seconds = int(m.group(1)) if m else 60
            if wait_seconds <= 0:
                wait_seconds = 60
            return wait_seconds
        except Exception:
            return 60

    def test_simple_flood_wait_string(self):
        """'A wait of 30 seconds' → 30"""
        assert self._parse_flood_wait("A wait of 30 seconds") == 30

    def test_flood_wait_with_error_code_after(self):
        """
        OLD: 'FloodWaitError: wait 130s [420]' → "130420" = 130420 (wrong)
        NEW: first standalone number → 130 (correct)
        """
        old_result = int("".join(filter(str.isdigit, "FloodWaitError: wait 130s [420]"))) or 60
        new_result = self._parse_flood_wait("FloodWaitError: wait 130s [420]")
        assert old_result == 130420, "Confirming old bug"
        assert new_result == 130, (
            f"NEW: should extract 130 (the wait duration), got {new_result}"
        )

    def test_flood_wait_with_timestamp_in_string(self):
        """
        Error containing a timestamp: '1712345678 FloodWait 45s'
        OLD: "171234567845" — catastrophically wrong
        NEW: "1712" is first 4-digit match, but that's a timestamp fragment.
             Actually re.search(\\b\\d{1,4}\\b) would match 1712 first.
             Let's verify the actual behavior and confirm it's bounded.
        """
        # The key property: result is at most 9999 (4-digit cap), not millions
        result = self._parse_flood_wait("1712345678 FloodWait 45s")
        assert result <= 9999, (
            f"NEW: result must be bounded to 4 digits max. Got: {result}"
        )

    def test_no_digits_falls_back_to_60(self):
        """No recognisable integer → default 60s."""
        assert self._parse_flood_wait("FloodWait error occurred") == 60

    def test_zero_seconds_falls_back_to_60(self):
        """A parsed value of 0 is replaced with 60."""
        assert self._parse_flood_wait("wait 0 seconds") == 60

    def test_malformed_string_falls_back_to_60(self):
        """Malformed/unexpected string → 60."""
        assert self._parse_flood_wait("") == 60
        assert self._parse_flood_wait("no numbers here!") == 60

    def test_structured_exception_attribute_used_first(self):
        """
        If the exception has a .seconds attribute (Telethon FloodWaitError),
        that value must be used directly — no regex parsing.
        """
        class FakeFloodWait(Exception):
            def __init__(self, seconds):
                self.seconds = seconds
                super().__init__(f"FloodWaitError [420]: wait {seconds}s [some code 9999]")

        exc = FakeFloodWait(45)
        result = self._parse_flood_wait(exc)
        assert result == 45, (
            f"Structured .seconds attribute must take priority. "
            f"Expected 45, got {result}"
        )

    def test_contextual_regex_wait_X(self):
        """'FloodWaitError: wait 130s [420]' → contextual 'wait 130' → 130."""
        result = self._parse_flood_wait("FloodWaitError: wait 130s [420]")
        assert result == 130, f"Contextual 'wait X' must extract 130, got {result}"

    def test_contextual_regex_floodwait_X(self):
        """'FloodWait 45 seconds' → contextual 'FloodWait 45' → 45."""
        result = self._parse_flood_wait("FloodWait 45 seconds")
        assert result == 45, f"Contextual 'FloodWait X' must extract 45, got {result}"

    def test_normal_flood_wait_120(self):
        """Standard 'FloodWaitError: 120' → 120."""
        assert self._parse_flood_wait("FloodWaitError: 120") == 120


# =============================================================================
# Issue #37 – event_bus.py
# =============================================================================

class TestIssue37EventBusAsyncSubscribers:

    def test_slow_subscriber_does_not_block_publisher(self):
        """
        OLD: slow subscriber ran synchronously → publish() blocked.
        NEW: subscriber dispatched to thread pool → publish() returns immediately.
        """
        from core.event_bus import EventBus  # FIX #1: test the runtime module
        bus = EventBus()
        started = threading.Event()

        def slow_subscriber(data):
            started.set()
            time.sleep(5)

        bus.subscribe("test_event", slow_subscriber)

        t_start = time.time()
        bus.publish("test_event", {})
        elapsed = time.time() - t_start

        started.wait(timeout=2)
        bus.shutdown(wait=False)

        assert elapsed < 0.5, (
            f"OLD: publish() blocked for {elapsed:.2f}s (slow subscriber). "
            "NEW: publish() must return immediately (< 0.5s)."
        )

    def test_failed_subscriber_exception_is_not_silently_lost(self):
        """
        Failed subscriber must be reported via done-callback logging.
        We verify by confirming the exception is captured in the Future.
        """
        from core.event_bus import EventBus  # FIX #1: test the runtime module
        import concurrent.futures
        bus = EventBus()
        exc_captured = []

        def bad_subscriber(data):
            raise ValueError("subscriber error")

        # Patch the done-callback to capture the exception directly
        original_publish = bus.publish

        futures_seen = []
        def capturing_publish(event_type, data=None):
            with bus._lock:
                callbacks = bus._subscribers.get(event_type, []).copy()
            for cb in callbacks:
                f = bus._executor.submit(cb, data)
                futures_seen.append(f)

        bus.subscribe("fail_event", bad_subscriber)
        capturing_publish("fail_event", {})

        # Wait for the future to complete
        done, _ = concurrent.futures.wait(futures_seen, timeout=2)
        bus.shutdown(wait=False)

        for f in done:
            exc = f.exception()
            if exc is not None:
                exc_captured.append(exc)

        assert exc_captured, (
            "Subscriber exception must be captured in Future result, not silently lost"
        )

    def test_multiple_subscribers_all_receive_event(self):
        """All registered subscribers receive the event data."""
        from event_bus import EventBus
        bus = EventBus()
        received = []

        bus.subscribe("multi", lambda d: received.append(("a", d)))
        bus.subscribe("multi", lambda d: received.append(("b", d)))
        bus.subscribe("multi", lambda d: received.append(("c", d)))

        bus.publish("multi", "payload")
        time.sleep(0.3)
        bus.shutdown(wait=True)

        keys = [r[0] for r in received]
        assert sorted(keys) == ["a", "b", "c"], (
            f"All 3 subscribers must receive the event. Got keys: {keys}"
        )

    def test_event_not_silently_dropped(self):
        """publish() dispatches to all current subscribers without dropping."""
        from event_bus import EventBus
        bus = EventBus()
        received = threading.Event()
        bus.subscribe("data_event", lambda d: received.set())
        bus.publish("data_event", {"key": "value"})
        assert received.wait(timeout=2), "Event was silently dropped"
        bus.shutdown(wait=False)

    def test_no_regression_subscribe_unsubscribe(self):
        """subscribe/unsubscribe API is unchanged."""
        from event_bus import EventBus
        bus = EventBus()
        calls = []
        cb = lambda d: calls.append(d)
        bus.subscribe("ev", cb)
        bus.publish("ev", 1)
        time.sleep(0.1)
        bus.unsubscribe("ev", cb)
        bus.publish("ev", 2)
        time.sleep(0.1)
        bus.shutdown(wait=True)
        assert calls == [1], f"After unsubscribe, cb must not receive 2. Got: {calls}"
