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


class MatchingClient:
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
                    "sizeMatched": float(size),
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class PartialClient:
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
                    "sizeMatched": float(size) / 2.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class RaisingClient:
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
        raise RuntimeError("recovery network crash")

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _payload(
    market_id="1.100",
    selection_id=10,
    bet_type="BACK",
    price=2.2,
    stake=8.0,
    event_name="A - B",
    market_name="Match Odds",
    runner_name="Runner A",
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
        "simulation_mode": False,
    }


def test_recovery_marks_partial_match_correctly():
    pending = [
        {
            "customer_ref": "REC-PARTIAL-1",
            "market_id": "1.200",
            "selection_id": 20,
            "raw_payload": json.dumps(
                _payload(
                    market_id="1.200",
                    selection_id=20,
                    stake=10.0,
                    runner_name="Runner Partial",
                )
            ),
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = PartialClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert len(client.calls) == 1
    assert db.reconciled == ["REC-PARTIAL-1"]
    assert db.failed == []
    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "PARTIALLY_MATCHED"

    success_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success_events) == 1
    assert success_events[0][1]["status"] == "PARTIALLY_MATCHED"


def test_recovery_handles_runtime_exception_and_marks_failed():
    pending = [
        {
            "customer_ref": "REC-ERR-1",
            "market_id": "1.300",
            "selection_id": 30,
            "raw_payload": json.dumps(
                _payload(
                    market_id="1.300",
                    selection_id=30,
                    runner_name="Runner Boom",
                )
            ),
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = RaisingClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert len(client.calls) == 1
    assert db.reconciled == []
    assert db.failed == ["REC-ERR-1"]
    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["status"] == "FAILED"

    failed_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_FAILED"]
    assert len(failed_events) == 1
    assert "recovery network crash" in failed_events[0][1]


def test_recovery_releases_lock_after_successful_reconcile():
    pending = [
        {
            "customer_ref": "REC-LOCK-1",
            "market_id": "1.400",
            "selection_id": 40,
            "raw_payload": json.dumps(
                _payload(
                    market_id="1.400",
                    selection_id=40,
                    runner_name="Runner Lock",
                )
            ),
            "status": "PENDING",
        }
    ]

    bus = DummyBus()
    db = DummyDB(pending=pending)
    client = MatchingClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert db.reconciled == ["REC-LOCK-1"]
    assert engine._acquire_lock("REC-LOCK-1") is True


def test_recovery_ignores_non_pending_rows():
    pending = [
        {
            "customer_ref": "DONE-1",
            "market_id": "1.500",
            "selection_id": 50,
            "raw_payload": json.dumps(_payload(market_id="1.500", selection_id=50)),
            "status": "RECONCILED",
        },
        {
            "customer_ref": "DONE-2",
            "market_id": "1.501",
            "selection_id": 51,
            "raw_payload": json.dumps(_payload(market_id="1.501", selection_id=51)),
            "status": "FAILED",
        },
    ]

    bus = DummyBus()
    db = DummyDB(pending=[])
    db.pending_sagas = pending
    client = MatchingClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    engine._recover_pending_sagas()

    assert client.calls == []
    assert db.reconciled == []
    assert db.failed == []
    assert db.saved_bets == []
    assert bus.events == []