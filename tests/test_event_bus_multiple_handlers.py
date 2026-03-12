from core.event_bus import EventBus


def test_multiple_handlers_receive_event():
    bus = EventBus()
    a, b = [], []

    bus.subscribe("EV", lambda p: a.append(p))
    bus.subscribe("EV", lambda p: b.append(p))

    bus.publish("EV", {"k": 1})

    assert len(a) == 1
    assert len(b) == 1