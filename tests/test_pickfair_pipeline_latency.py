
from core.fast_analytics import FastWoMState
from core.perf_counters import now_ns
from core.tick_ring_buffer import TickRingBuffer


def test_pipeline_latency_under_1ms_average():

    buf = TickRingBuffer(maxlen=5000)
    wom = FastWoMState(max_ticks=128)

    loops = 2000

    total_ns = 0

    for _i in range(loops):

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

        wom.push(
            {
                "back_volume": tick["back_volume"],
                "lay_volume": tick["lay_volume"],
            }
        )

        _ = wom.wom()

        elapsed = now_ns() - t0

        total_ns += elapsed

    avg_ns = total_ns / loops

    avg_us = avg_ns / 1000

    assert avg_us < 1000