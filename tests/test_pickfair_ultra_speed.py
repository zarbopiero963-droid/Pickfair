import time

from core.fast_analytics import FastWoMState
from core.perf_counters import PerfCounters
from core.tick_ring_buffer import TickRingBuffer


def test_ring_buffer_push_pop_10000_under_threshold():

    buf = TickRingBuffer(maxlen=20000)

    start = time.perf_counter()

    for i in range(10000):
        buf.push(
            {
                "i": i,
                "back_volume": 100.0,
                "lay_volume": 80.0,
            }
        )

    count = 0

    while len(buf):
        item = buf.pop()
        assert item is not None
        count += 1

    elapsed = time.perf_counter() - start

    assert count == 10000
    assert elapsed < 0.10


def test_fast_wom_rolling_10000_ticks():

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

        assert wom > 0

    elapsed = time.perf_counter() - start

    assert elapsed < 0.10


def test_perf_counter_overhead():

    perf = PerfCounters()

    start = time.perf_counter()

    for _ in range(10000):
        perf.add("analytics_ns", 500)

    stats = perf.stats()

    elapsed = time.perf_counter() - start

    assert stats["analytics_ns"]["count"] == 2000
    assert elapsed < 0.05