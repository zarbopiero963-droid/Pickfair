from controllers.dutching_controller import DutchingController


class DummyBus:

    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


def test_controller_publishes_event():
    bus = DummyBus()

    controller = DutchingController(bus)

    payload = {
        "market_id": "1.1",
        "results": [
            {"selectionId": 1, "price": 2.0, "stake": 10}
        ]
    }

    controller.execute(payload)

    assert len(bus.events) == 1