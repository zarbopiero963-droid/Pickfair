import json

import pytest

from circuit_breaker import PermanentError
from core.safety_layer import SafetyLayer, RiskInvariantError
from core.trading_engine import TradingEngine
from pnl_engine import PnLEngine


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
        self.saved_cashouts = []
        self.sim_settings = {"virtual_balance": 1000.0}
        self.sim_saved = []
        self.sim_balance_updates = []
        self.reconciled = []
        self.failed = []

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
        return [x for x in self.pending_sagas if x["status"] == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)
        for saga in self.pending_sagas:
            if saga["customer_ref"] == customer_ref:
                saga["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)
        for saga in self.pending_sagas:
            if saga["customer_ref"] == customer_ref:
                saga["status"] = "FAILED"

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

    def save_cashout_transaction(self, **kwargs):
        self.saved_cashouts.append(kwargs)

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        self.sim_saved.append(kwargs)

    def increment_simulation_bet_count(self, new_balance):
        self.sim_balance_updates.append(new_balance)
        self.sim_settings["virtual_balance"] = new_balance


class RecoveryClient:
    def __init__(self, *, recovered_order=None, place_error=None):
        self.place_error = place_error
        self.recovered_order = recovered_order
        self.place_bet_calls = []
        self.get_current_orders_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.place_orders_calls = []
        self.market_book = {"runners": []}

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
        self.place_bet_calls.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "side": side,
                "price": price,
                "size": size,
                "customer_ref": customer_ref,
            }
        )
        if self.place_error is not None:
            raise self.place_error
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET_{selection_id}",
                    "sizeMatched": size,
                }
            ],
        }

    def place_orders(self, market_id, instructions, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
                "customer_ref": customer_ref,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET_{idx}",
                    "sizeMatched": i["limitOrder"]["size"],
                }
                for idx, i in enumerate(instructions, start=1)
            ],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": instructions[0]["betId"],
                    "sizeMatched": 0.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        self.get_current_orders_calls.append({"args": args, "kwargs": kwargs})
        if self.recovered_order is None:
            return {"currentOrders": [], "matched": [], "unmatched": []}
        return {
            "currentOrders": [self.recovered_order],
            "matched": [],
            "unmatched": [],
        }

    def get_market_book(self, market_id):
        return self.market_book


class ReplaceFailClient(RecoveryClient):
    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        raise ConnectionError("replace failed hard")


class CashoutPermanentErrorClient(RecoveryClient):
    def place_orders(self, market_id, instructions, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
                "customer_ref": customer_ref,
            }
        )
        raise PermanentError("circuit open")


@pytest.fixture
def bus():
    return DummyBus()


@pytest.fixture
def db():
    return DummyDB()


@pytest.fixture
def executor():
    return DummyExecutor()


def _make_engine(bus, db, client, executor):
    return TradingEngine(bus, db, lambda: client, executor)


def test_quick_bet_recovery_after_broker_disconnect_marks_reconciled_and_publishes_recovered_success(
    bus, db, executor
):
    client = RecoveryClient(
        place_error=ConnectionError("socket reset after submit"),
        recovered_order={
            "customerOrderRef": None,
            "marketId": "1.200",
            "sizeMatched": 10.0,
        },
    )
    engine = _make_engine(bus, db, client, executor)

    payload = {
        "market_id": "1.200",
        "selection_id": 77,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "event_name": "Inter - Milan",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }

    original_place_bet = client.place_bet

    def wrapped_place_bet(*args, **kwargs):
        customer_ref = kwargs.get("customer_ref")
        client.recovered_order["customerOrderRef"] = customer_ref
        client.recovered_order["customerRef"] = customer_ref
        return original_place_bet(*args, **kwargs)

    client.place_bet = wrapped_place_bet

    engine._handle_quick_bet(payload)

    success_events = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success_events) == 1

    success_payload = success_events[0][1]
    assert success_payload["recovered"] is True
    assert success_payload["status"] == "MATCHED"
    assert success_payload["matched"] == 10.0

    assert db.saved_bets[-1]["status"] == "MATCHED"
    assert len(db.reconciled) == 1
    assert client.get_current_orders_calls


def test_quick_bet_microstake_replace_failure_rolls_back_and_fails_closed(
    bus, db, executor
):
    client = ReplaceFailClient()
    engine = _make_engine(bus, db, client, executor)

    payload = {
        "market_id": "1.300",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.12,
        "stake": 0.5,
        "event_name": "Roma - Lazio",
        "market_name": "Match Odds",
        "runner_name": "Roma",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    failed = [evt for evt in bus.events if evt[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]

    assert len(client.cancel_orders_calls) == 2
    assert client.cancel_orders_calls[0]["instructions"][0]["sizeReduction"] == pytest.approx(1.5)
    assert "sizeReduction" not in client.cancel_orders_calls[1]["instructions"][0]

    assert db.saved_bets[-1]["status"] == "FAILED"
    assert len(db.failed) == 1


def test_dutching_use_best_price_applies_market_book_to_normal_orders_and_micro_orders(
    bus, db, executor
):
    client = RecoveryClient()
    client.market_book = {
        "runners": [
            {
                "selectionId": 11,
                "ex": {
                    "availableToBack": [{"price": 2.22, "size": 50}],
                    "availableToLay": [{"price": 2.3, "size": 20}],
                },
            },
            {
                "selectionId": 22,
                "ex": {
                    "availableToBack": [{"price": 3.55, "size": 50}],
                    "availableToLay": [{"price": 3.7, "size": 20}],
                },
            },
        ]
    }
    engine = _make_engine(bus, db, client, executor)

    payload = {
        "market_id": "1.400",
        "bet_type": "BACK",
        "total_stake": 2.5,
        "use_best_price": True,
        "simulation_mode": False,
        "results": [
            {"selectionId": 11, "runnerName": "A", "price": 9.9, "stake": 2.0},
            {"selectionId": 22, "runnerName": "B", "price": 9.9, "stake": 0.5},
        ],
    }

    engine._handle_place_dutching(payload)

    assert len(client.place_orders_calls) == 1
    normal_instructions = client.place_orders_calls[0]["instructions"]
    assert normal_instructions[0]["limitOrder"]["price"] == pytest.approx(2.22)

    assert len(client.place_bet_calls) == 1
    assert client.place_bet_calls[0]["selection_id"] == 22
    assert client.place_bet_calls[0]["price"] == pytest.approx(1.01)

    success = [evt for evt in bus.events if evt[0] == "DUTCHING_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["matched"] == pytest.approx(2.0)
    assert db.saved_bets[-1]["status"] == "PARTIALLY_MATCHED"


def test_cashout_permanent_error_triggers_safe_mode_event_and_fail_closed(
    bus, db, executor
):
    client = CashoutPermanentErrorClient()
    engine = _make_engine(bus, db, client, executor)

    payload = {
        "market_id": "1.500",
        "selection_id": 9,
        "side": "LAY",
        "stake": 5.0,
        "price": 2.4,
        "green_up": 1.25,
    }

    engine._handle_cashout(payload)

    failed = [evt for evt in bus.events if evt[0] == "CASHOUT_FAILED"]
    safe_mode = [evt for evt in bus.events if evt[0] == "SAFE_MODE_TRIGGER"]

    assert len(failed) == 1
    assert "Errore Rete" in failed[0][1]

    assert len(safe_mode) == 1
    assert safe_mode[0][1]["reason"] == "Circuit Breaker Cashout"

    assert db.saved_cashouts == []
    assert len(db.failed) == 1


def test_recover_pending_sagas_cleans_stub_micro_orders_and_marks_saga_reconciled(
    bus, db, executor
):
    client = RecoveryClient(
        recovered_order={
            "customerOrderRef": "ref-stub",
            "customerRef": "ref-stub",
            "marketId": "1.600",
            "price": 1.01,
            "sizeRemaining": 2.0,
            "sizeMatched": 0.0,
            "betId": "BET-STUB",
        }
    )
    engine = _make_engine(bus, db, client, executor)

    db.pending_sagas.append(
        {
            "customer_ref": "ref-stub",
            "market_id": "1.600",
            "selection_id": 33,
            "raw_payload": json.dumps(
                {
                    "market_id": "1.600",
                    "selection_id": 33,
                    "bet_type": "BACK",
                    "price": 2.2,
                    "stake": 0.5,
                    "runner_name": "Runner",
                    "event_name": "Recovered Event",
                    "market_name": "Match Odds",
                }
            ),
            "status": "PENDING",
        }
    )

    engine._recover_pending_sagas()

    assert len(client.cancel_orders_calls) == 1
    assert client.cancel_orders_calls[0]["instructions"] == [{"betId": "BET-STUB"}]

    assert db.pending_sagas[0]["status"] == "RECONCILED"
    assert db.saved_bets[-1]["event_name"] == "Recovered Event"


def test_safety_layer_rejects_negative_matched_cashout_success_and_detects_stale_sagas():
    safety = SafetyLayer()

    with pytest.raises(RiskInvariantError, match="matched < 0"):
        safety.validate_cashout_success(
            {
                "green_up": 1.2,
                "matched": -0.1,
                "status": "MATCHED",
            }
        )

    class SagaDB:
        def get_pending_sagas(self):
            return [
                {
                    "customer_ref": "r1",
                    "market_id": "1.1",
                    "selection_id": 7,
                    "status": "PENDING",
                    "created_at": 1.0,
                    "raw_payload": "{}",
                },
                {
                    "customer_ref": "r2",
                    "market_id": "1.2",
                    "selection_id": 8,
                    "status": "RECONCILED",
                    "created_at": 9999999999.0,
                    "raw_payload": "{}",
                },
            ]

    stale = safety.get_stale_pending_sagas(SagaDB(), stale_after_sec=10.0)
    assert len(stale) == 1
    assert stale[0].customer_ref == "r1"


def test_pnl_engine_uses_matched_size_and_average_price_over_stake_and_price():
    engine = PnLEngine(commission=4.5)

    order = {
        "side": "BACK",
        "stake": 2.0,
        "price": 10.0,
        "sizeMatched": 5.0,
        "averagePriceMatched": 3.0,
    }

    pnl_from_matched = engine.calculate_back_pnl(order, best_lay_price=2.5)
    pnl_from_raw = engine.calculate_back_pnl(
        {"side": "BACK", "stake": 5.0, "price": 3.0},
        best_lay_price=2.5,
    )

    assert pnl_from_matched == pnl_from_raw
    assert pnl_from_matched != 0.0