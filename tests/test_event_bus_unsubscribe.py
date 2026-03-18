from event_bus import EventBus


def test_unsubscribe_removes_handler():

    bus = EventBus()

    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("A", handler)

    bus.unsubscribe("A", handler)

    bus.publish("A", {"x": 1})

    assert received == []