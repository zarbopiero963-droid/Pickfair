import importlib

market_tracker_mod = importlib.import_module("core.market_tracker")
MarketTracker = market_tracker_mod.MarketTracker


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def publish(self, event, payload):
        self.events.append((event, payload))
        for h in self.subscribers.get(event, []):
            h(payload)

    def subscribe(self, event, handler):
        self.subscribers.setdefault(event, []).append(handler)


def test_market_tracker_stream_update_dispatch():
    bus = DummyBus()

    tracker = MarketTracker(bus=bus)

    updates = []

    def subscriber(payload):
        updates.append(payload)

    bus.subscribe("MARKET_UPDATE", subscriber)

    tick = {
        "marketId": "1.100",
        "runners": [
            {"selectionId": 11, "price": 2.0},
            {"selectionId": 22, "price": 3.5},
        ],
    }

    tracker.on_market_tick(tick)

    assert len(updates) == 1
    assert updates[0]["marketId"] == "1.100"