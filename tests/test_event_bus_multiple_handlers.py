from event_bus import EventBus


def test_multiple_subscribers_receive_event():

    bus = EventBus()

    a = []
    b = []

    bus.subscribe("X", lambda p: a.append(p))
    bus.subscribe("X", lambda p: b.append(p))

    bus.publish("X", {"v": 1})

    assert a == [{"v": 1}]
    assert b == [{"v": 1}]