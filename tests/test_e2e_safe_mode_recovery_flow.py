from core.trading_engine import TradingEngine
from circuit_breaker import PermanentError


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
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []
        self.failed = []
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
        return None

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)

    def save_bet(
        self,
        event_name,
        market_id,
        market_name,
        bet_type,
        selections,
        total_stake,
        potential_profit,
        status,
    ):
        self.saved_bets.append(
            {
                "event_name": event_name,
                "market_id": market_id,
                "market_name": market_name,
                "bet_type": bet_type,
                "selections": selections,
                "total_stake": total_stake,
                "potential_profit": potential_profit,
                "status": status,
            }
        )

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, new_balance):
        self.sim_settings["virtual_balance"] = new_balance

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class FailingClient:
    def place_bet(self, **kwargs):
        raise PermanentError("circuit open")

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def test_e2e_safe_mode_recovery_flow_triggers_block():
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: FailingClient(), DummyExecutor())

    payload = {
        "market_id": "1.800",
        "selection_id": 80,
        "bet_type": "BACK",
        "price": 2.0,
        "stake": 10.0,
        "event_name": "Risk Match",
        "market_name": "Match Odds",
        "runner_name": "Runner Risk",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    safe_mode = [evt for evt in bus.events if evt[0] == "SAFE_MODE_TRIGGER"]
    failed = [evt for evt in bus.events if evt[0] == "QUICK_BET_FAILED"]

    assert len(safe_mode) == 1
    assert safe_mode[0][1]["reason"] == "Circuit Breaker"
    assert "circuit open" in safe_mode[0][1]["details"]

    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]

    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"