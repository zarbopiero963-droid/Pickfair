import threading
import time

from core.event_bus import EventBus


def test_event_bus_many_messages():
    bus = EventBus()

    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("TEST_EVENT", handler)

    for i in range(1000):
        bus.publish("TEST_EVENT", {"n": i})

    time.sleep(0.05)

    assert len(received) == 1000