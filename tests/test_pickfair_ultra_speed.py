import time

from core.perf_counters import PerfCounters, now_ns
from core.tick_ring_buffer import TickRingBuffer
from core.fast_analytics import FastWoMState


def test_ring_buffer_push_pop_10000_under_threshold():
    buf = TickRingBuffer(maxlen=20000)

    start = time.perf_counter()
    for i in range(10000):
        buf.push({"i": i, "back_volume": 100.0, "lay_volume": 80.0})

    count = 0
    while len(buf):
        item = buf.pop()
        assert item is not None
        count += 1

    elapsed = time.perf_counter() - start

    assert count == 10000
    assert elapsed < 0.10


def test_fast_wom_rolling_10000_ticks_under_threshold():
    state = FastWoMState(max_ticks=256)

    start = time.perf_counter()
    for _ in range(10000):
        state.push(
            {
                "back_volume": 150.0,
                "lay_volume": 90.0,
            }
        )
        wom = state.wom()
        assert wom > 0.0
    elapsed = time.perf_counter() - start

    assert elapsed < 0.10


def test_perf_counters_recording_is_light():
    perf = PerfCounters()

    start = time.perf_counter()
    for _ in range(10000):
        perf.add("analytics_ns", 500)
    stats = perf.stats()
    elapsed = time.perf_counter() - start

    assert stats["analytics_ns"]["count"] == 2000
    assert elapsed < 0.05


def test_simulated_tick_pipeline_under_1ms_average():
    buf = TickRingBuffer(maxlen=5000)
    perf = PerfCounters()
    state = FastWoMState(max_ticks=128)

    total_ns = 0
    loops = 2000

    for i in range(loops):
        t0 = now_ns()

        buf.push(
            {
                "selection_id": 1,
                "back_price": 2.0,
                "back_volume": 120.0,
                "lay_price": 2.02,
                "lay_volume": 80.0,
            }
        )

        tick = buf.pop()
        state.push(tick)
        wom = state.wom()
        assert wom > 0.0

        elapsed_ns = now_ns() - t0
        perf.add("analytics_ns", elapsed_ns)
        total_ns += elapsed_ns

    avg_ns = total_ns / loops
    avg_us = avg_ns / 1000.0

    assert avg_us < 1000.0