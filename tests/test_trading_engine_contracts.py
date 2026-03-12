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
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending_sagas.append((customer_ref, market_id, selection_id, payload))

    def get_pending_sagas(self):
        return []

    def mark_saga_reconciled(self, _customer_ref):
        return None

    def mark_saga_failed(self, _customer_ref):
        return None

    def save_bet(self, **kwargs):
        self.saved_bets.append(kwargs)

    def get_simulation_settings(self):
        return {"virtual_balance": 1000.0}

    def save_simulation_bet(self, **kwargs):
        self.saved_bets.append(kwargs)

    def increment_simulation_bet_count(self, _new_balance):
        return None

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class DummyClient:
    def place_bet(self, **kwargs):
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "BET1", "sizeMatched": kwargs["size"]}],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()
    return TradingEngine(bus, db, lambda: client, executor), bus, db


def test_trading_engine_quick_bet_success_payload_contract():
    engine, bus, _db = _make_engine()
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

    event_name, event_payload = [x for x in bus.events if x[0] == "QUICK_BET_SUCCESS"][0]
    assert event_name == "QUICK_BET_SUCCESS"
    for key in [
        "market_id", "selection_id", "event_name", "market_name",
        "bet_type", "runner_name", "price", "stake", "matched", "status", "sim", "micro"
    ]:
        assert key in event_payload


def test_trading_engine_simulation_contract_has_balance_fields():
    engine, bus, _db = _make_engine()
    payload = {
        "market_id": "1.1",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.0,
        "stake": 5.0,
        "event_name": "A - B",
        "market_name": "Match Odds",
        "runner_name": "A",
        "simulation_mode": True,
    }
    engine._handle_quick_bet(payload)
    _, event_payload = [x for x in bus.events if x[0] == "QUICK_BET_SUCCESS"][0]
    assert event_payload["sim"] is True
    assert "new_balance" in event_payload
