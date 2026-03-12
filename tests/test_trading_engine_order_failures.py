from core.trading_engine import TradingEngine


class DummyBus:
    def __init__(self):
        self.subscribers = {}
        self.events = []

    def subscribe(self, event_name, handler):
        self.subscribers.setdefault(event_name, []).append(handler)

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))
        for handler in self.subscribers.get(event_name, []):
            handler(payload)


class DummyExecutor:
    def submit(self, _name, fn):
        return fn()


class DummyDB:
    def create_pending_saga(self, *args, **kwargs):
        return None

    def get_pending_sagas(self):
        return []

    def mark_saga_reconciled(self, *_args, **_kwargs):
        return None

    def mark_saga_failed(self, *_args, **_kwargs):
        return None

    def save_bet(self, *args, **kwargs):
        return None

    def get_simulation_settings(self):
        return {"virtual_balance": 1000.0}

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, _new_balance):
        return None

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class FailingClient:
    def place_bet(self, **kwargs):
        raise Exception("network timeout")

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def test_trading_engine_failure_publishes_quick_bet_failed():
    bus = DummyBus()
    engine = TradingEngine(bus, DummyDB(), lambda: FailingClient(), DummyExecutor())

    payload = {
        "market_id": "1.1",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "event_name": "A - B",
        "market_name": "Match Odds",
        "runner_name": "A",
        "simulation_mode": False,
    }
    engine._handle_quick_bet(payload)

    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]


def test_trading_engine_safe_mode_blocks_quick_bet():
    bus = DummyBus()
    engine = TradingEngine(bus, DummyDB(), lambda: FailingClient(), DummyExecutor())
    engine.is_killed = True

    payload = {
        "market_id": "1.1",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
    }
    engine._handle_quick_bet(payload)

    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]
    assert failed[0][1] == "SAFE MODE ATTIVO"
