import pytest

from core.tick_ring_buffer import TickRingBuffer


def test_tick_burst_insert():
    buf = TickRingBuffer(size=100)

    for i in range(500):
        buf.add_tick({"price": 2.0 + i * 0.001})

    assert buf.count() <= 100