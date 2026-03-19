from circuit_breaker import PermanentError
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
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []
        self.failed_refs = []
        self.reconciled_refs = []
        self.sim_settings = {"virtual_balance": 1000.0}

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending_sagas.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": "{}",
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return []

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled_refs.append(customer_ref)

    def mark_saga_failed(self, customer_ref):
        self.failed_refs.append(customer_ref)

    def save_bet(self, **kwargs):
        self.saved_bets.append(kwargs)

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, _new_balance):
        return None

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class FailingClient:
    def place_bet(self, **kwargs):
        raise RuntimeError("network timeout")

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class PermanentFailingClient:
    def place_bet(self, **kwargs):
        raise PermanentError("circuit open")

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class ApiRejectClient:
    def place_bet(self, **kwargs):
        return {"status": "FAILURE", "instructionReports": []}

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _payload():
    return {
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


def test_trading_engine_failure_publishes_quick_bet_failed():
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: FailingClient(), DummyExecutor())

    engine._handle_quick_bet(_payload())

    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]
    assert "network timeout" in failed[0][1]
    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"
    assert len(db.failed_refs) == 1


def test_trading_engine_safe_mode_blocks_quick_bet():
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: FailingClient(), DummyExecutor())
    engine.is_killed = True

    engine._handle_quick_bet(_payload())

    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]
    assert failed == [("QUICK_BET_FAILED", "SAFE MODE ATTIVO")]
    assert db.saved_bets == []
    assert db.failed_refs == []


def test_trading_engine_api_failure_marks_saga_failed_and_saves_failed_bet():
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: ApiRejectClient(), DummyExecutor())

    engine._handle_quick_bet(_payload())

    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert failed[0][1] == "Stato API: FAILURE"
    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"
    assert len(db.failed_refs) == 1


def test_trading_engine_permanent_error_triggers_safe_mode_event():
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: PermanentFailingClient(), DummyExecutor())

    engine._handle_quick_bet(_payload())

    safe_mode = [x for x in bus.events if x[0] == "SAFE_MODE_TRIGGER"]
    failed = [x for x in bus.events if x[0] == "QUICK_BET_FAILED"]

    assert len(safe_mode) == 1
    assert safe_mode[0][1]["reason"] == "Circuit Breaker"
    assert "circuit open" in safe_mode[0][1]["details"]

    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]
    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"