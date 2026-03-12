from core.event_bus import EventBus


def test_unsubscribe_handler():
    bus = EventBus()
    calls = []

    def handler(payload):
        calls.append(payload)

    bus.subscribe("X", handler)
    bus.unsubscribe("X", handler)

    bus.publish("X", {"a": 1})

    assert calls == []