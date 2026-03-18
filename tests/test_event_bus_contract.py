from event_bus import EventBus


def test_publish_subscribe_contract():

    bus = EventBus()
    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("TEST", handler)

    bus.publish("TEST", {"a": 1})

    assert received == [{"a": 1}]