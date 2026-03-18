import importlib

engine_mod = importlib.import_module("core.trading_engine")
TradingEngine = engine_mod.TradingEngine


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def publish(self, event, payload):
        self.events.append((event, payload))

    def subscribe(self, event, handler):
        self.subscribers.setdefault(event, []).append(handler)


class DummyDB:
    def __init__(self):
        self.balance = 1000

    def get_simulation_settings(self):
        return {"virtual_balance": self.balance}

    def increment_simulation_bet_count(self, new_balance):
        self.balance = new_balance

    def save_simulation_bet(self, **kwargs):
        return kwargs


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def test_simulation_runtime_flow():
    bus = DummyBus()
    db = DummyDB()

    engine = TradingEngine(bus, db, lambda: None, DummyExecutor())

    payload = {
        "market_id": "1.500",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2,
        "stake": 50,
        "event_name": "Sim Match",
        "market_name": "Match Odds",
        "runner_name": "Runner",
        "simulation_mode": True,
    }

    engine._handle_quick_bet(payload)

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]

    assert len(success) == 1
    assert db.balance == 950