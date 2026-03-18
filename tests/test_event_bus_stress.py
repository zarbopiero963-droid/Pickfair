from event_bus import EventBus


def test_event_bus_many_events():

    bus = EventBus()

    counter = {"v": 0}

    def handler(_):
        counter["v"] += 1

    bus.subscribe("EV", handler)

    for _ in range(1000):
        bus.publish("EV", {})

    assert counter["v"] == 1000