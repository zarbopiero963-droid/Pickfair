import json

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
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self, pending=None):
        self.pending_sagas = list(pending or [])
        self.reconciled = []
        self.failed = []
        self.saved_bets = []
        self.sim_settings = {"virtual_balance": 1000.0}

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending_sagas.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": json.dumps(payload),
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return [row for row in self.pending_sagas if row.get("status") == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)
        for row in self.pending_sagas:
            if row["customer_ref"] == customer_ref:
                row["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)
        for row in self.pending_sagas:
            if row["customer_ref"] == customer_ref:
                row["status"] = "FAILED"

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


class SuccessfulClient:
    def __init__(self):
        self.calls = []

    def place_bet(
        self,
        market_id,
        selection_id,
        side,
        price,
        size,
        persistence_type="LAPSE",
        customer_ref=None,
    ):
        self.calls.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "side": side,
                "price": price,
                "size": size,
                "customer_ref": customer_ref,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{selection_id}",
                    "sizeMatched": size,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class RejectingClient:
    def __init__(self):
        self.calls = []

    def place_bet(
        self,
        market_id,
        selection_id,
        side,
        price,
        size,
        persistence_type="LAPSE",
        customer_ref=None,
    ):
        self.calls.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "side": side,
                "price": price,
                "size": size,
                "customer_ref": customer_ref,
            }
        )
        return {
            "status": "FAILURE",
            "instructionReports": [],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_payload(
    market_id="1.111",
    selection_id=11,
    bet_type="BACK",
    price=2.5,
    stake=10.0,
    event_name="Juve - Milan",
    market_name="Match Odds",
    runner_name="Juve",
    simulation_mode=False,
):
    return {
        "market_id": market_id,
        "selection_id": selection_id,
        "bet_type": bet_type,
        "price": price,
        "stake": stake,
        "event_name": event_name,
        "market_name": market_name,
        "runner_name": runner_name,
        "simulation_mode": simulation_mode,
    }


def test_recover_pending_sagas_reconciles_successful_rows():
    pending = [
        {
            "customer_ref": "REC-1",
            "market_id": "1.111",
            "selection_id": 11,
            "raw_payload": json.dumps(_make_payload()),
            "status": "PENDING",
        },
        {
            "customer_ref": "REC-2",
            "market_id": "1.222",
            "selection_id": 22,
            "raw_payload": json.dumps(
                _make_payload(
                    market_id="1.222",
                    selection_id=22,
                    runner_name="Milan",
                    stake=5.0,
                )
            ),
            "status": "PENDING",
        },
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = SuccessfulClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert len(client.calls) == 2
    assert db.reconciled == ["REC-1", "REC-2"]
    assert db.failed == []

    success_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success_events) == 2

    assert len(db.saved_bets) == 2
    assert db.saved_bets[0]["status"] == "MATCHED"
    assert db.saved_bets[1]["status"] == "MATCHED"


def test_recover_pending_sagas_marks_failed_when_api_rejects():
    pending = [
        {
            "customer_ref": "FAIL-1",
            "market_id": "1.333",
            "selection_id": 33,
            "raw_payload": json.dumps(
                _make_payload(
                    market_id="1.333",
                    selection_id=33,
                    runner_name="Runner X",
                )
            ),
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = RejectingClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert len(client.calls) == 1
    assert db.reconciled == []
    assert db.failed == ["FAIL-1"]

    failed_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_FAILED"]
    assert len(failed_events) == 1
    assert failed_events[0][1] == "Stato API: FAILURE"

    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"


def test_recover_pending_sagas_skips_when_no_pending_rows():
    bus = DummyBus()
    db = DummyDB(pending=[])
    client = SuccessfulClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert client.calls == []
    assert db.reconciled == []
    assert db.failed == []
    assert db.saved_bets == []
    assert bus.events == []


def test_recovery_does_not_duplicate_locked_customer_ref():
    pending = [
        {
            "customer_ref": "LOCK-1",
            "market_id": "1.444",
            "selection_id": 44,
            "raw_payload": json.dumps(
                _make_payload(
                    market_id="1.444",
                    selection_id=44,
                    runner_name="Runner Y",
                )
            ),
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = SuccessfulClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    assert engine._acquire_lock("LOCK-1") is True

    engine._recover_pending_sagas()

    assert client.calls == []
    assert db.reconciled == []
    assert db.failed == []
    assert db.saved_bets == []
    assert bus.events == []


def test_recovery_handles_corrupted_payload_as_failed():
    pending = [
        {
            "customer_ref": "BAD-1",
            "market_id": "1.555",
            "selection_id": 55,
            "raw_payload": "{not-valid-json",
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = SuccessfulClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert client.calls == []
    assert db.reconciled == []
    assert db.failed == ["BAD-1"]

    failed_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_FAILED"]
    assert len(failed_events) == 1
    assert "recupero" in failed_events[0][1].lower() or "json" in failed_events[0][1].lower()