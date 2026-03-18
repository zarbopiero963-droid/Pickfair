import threading


class DummyBroker:
    def __init__(self):
        self.orders = []

    def place_order(self, payload):
        self.orders.append(payload)
        return {"status": "SUCCESS"}


class DummyEngine:
    def __init__(self, broker):
        self.broker = broker

    def _handle_quick_bet(self, payload):
        self.broker.place_order(payload)


def test_concurrency_stress():
    broker = DummyBroker()
    engine = DummyEngine(broker)

    payload = {
        "market_id": "1.200",
        "selection_id": 10,
        "bet_type": "BACK",
        "price": 2,
        "stake": 5,
        "event_name": "Test",
        "market_name": "Odds",
        "runner_name": "Runner",
        "simulation_mode": False,
    }

    threads = []

    for _ in range(10):
        t = threading.Thread(target=engine._handle_quick_bet, args=(payload,))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 10