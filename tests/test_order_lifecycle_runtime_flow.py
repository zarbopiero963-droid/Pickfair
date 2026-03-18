import importlib

engine_mod = importlib.import_module("core.trading_engine")
TradingEngine = engine_mod.TradingEngine


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


class DummyDB:
    def __init__(self):
        self.saved = []

    def save_bet(self, **kwargs):
        self.saved.append(kwargs)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyClient:
    def place_bet(self, **kwargs):
        return {
            "status": "SUCCESS",
            "instructionReports": [{"sizeMatched": kwargs["size"]}],
        }


def test_order_lifecycle_full():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    payload = {
        "market_id": "1.200",
        "selection_id": 10,
        "bet_type": "BACK",
        "price": 2.1,
        "stake": 5,
        "event_name": "Test Match",
        "market_name": "Match Odds",
        "runner_name": "Team A",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]

    assert len(success) == 1
    assert len(db.saved) == 1