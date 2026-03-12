from core.event_bus import EventBus


def test_event_bus_subscribe_publish_unsubscribe():
    bus = EventBus()
    received = []

    def cb(data):
        received.append(data)

    bus.subscribe("EVT", cb)
    bus.publish("EVT", {"x": 1})
    assert received == [{"x": 1}]

    bus.unsubscribe("EVT", cb)
    bus.publish("EVT", {"x": 2})
    assert received == [{"x": 1}]


def test_event_bus_prevents_duplicate_subscriber_registration():
    bus = EventBus()
    received = []

    def cb(data):
        received.append(data)

    bus.subscribe("EVT", cb)
    bus.subscribe("EVT", cb)
    bus.publish("EVT", 123)
    assert received == [123]


def test_event_bus_continues_when_one_subscriber_fails():
    bus = EventBus()
    received = []

    def bad(_data):
        raise RuntimeError("boom")

    def good(data):
        received.append(data)

    bus.subscribe("EVT", bad)
    bus.subscribe("EVT", good)
    bus.publish("EVT", "ok")
    assert received == ["ok"]
