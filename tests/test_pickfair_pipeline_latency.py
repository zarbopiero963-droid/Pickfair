import time

from core.tick_ring_buffer import TickRingBuffer
from core.fast_analytics import FastWoMState


def test_pipeline_burst_5000_ticks():
    buf = TickRingBuffer(maxlen=10000)
    wom = FastWoMState(max_ticks=256)

    start = time.perf_counter()

    for i in range(5000):
        buf.push(
            {
                "selection_id": (i % 10) + 1,
                "back_price": 2.0,
                "back_volume": 100.0 + (i % 5),
                "lay_price": 2.02,
                "lay_volume": 80.0 + (i % 5),
            }
        )

    processed = 0
    while len(buf):
        tick = buf.pop()
        wom.push(
            {
                "back_volume": tick["back_volume"],
                "lay_volume": tick["lay_volume"],
            }
        )
        _ = wom.wom()
        processed += 1

    elapsed = time.perf_counter() - start

    assert processed == 5000
    assert elapsed < 0.20