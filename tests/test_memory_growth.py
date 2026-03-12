from core.tick_ring_buffer import TickRingBuffer


def test_ring_buffer_memory_bound():
    buf = TickRingBuffer(size=50)

    for i in range(1000):
        buf.add_tick({"p": i})

    assert buf.count() == 50