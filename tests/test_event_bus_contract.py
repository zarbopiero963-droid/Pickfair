from core.event_bus import EventBus


def test_event_bus_publish_and_receive():
    bus = EventBus()

    received = {}

    def handler(payload):
        received["payload"] = payload

    bus.subscribe("TEST_EVENT", handler)

    payload = {"value": 123}

    bus.publish("TEST_EVENT", payload)

    assert "payload" in received
    assert received["payload"] == payload


def test_event_bus_multiple_subscribers_receive_event():
    bus = EventBus()

    counter = {"a": 0, "b": 0}

    def handler_a(payload):
        counter["a"] += 1

    def handler_b(payload):
        counter["b"] += 1

    bus.subscribe("MULTI_EVENT", handler_a)
    bus.subscribe("MULTI_EVENT", handler_b)

    bus.publish("MULTI_EVENT", {"x": 1})

    assert counter["a"] == 1
    assert counter["b"] == 1


def test_event_bus_unsubscribe():
    bus = EventBus()

    counter = {"count": 0}

    def handler(payload):
        counter["count"] += 1

    bus.subscribe("EV", handler)
    bus.unsubscribe("EV", handler)

    bus.publish("EV", {})

    assert counter["count"] == 0