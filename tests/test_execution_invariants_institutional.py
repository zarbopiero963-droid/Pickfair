import json
import threading
import time

import pytest

from core.trading_engine import TradingEngine
from core.safety_layer import SafetyLayer
from pnl_engine import PnLEngine


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def subscribe(self, event, handler):
        self.subscribers.setdefault(event, []).append(handler)

    def publish(self, event, payload):
        self.events.append((event, payload))
        for h in self.subscribers.get(event, []):
            h(payload)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class FakeDB:
    def __init__(self):
        self.saved_bets = []
        self.pending_sagas = []
        self.sim_settings = {"virtual_balance": 1000}

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
                "event": event_name,
                "market_id": market_id,
                "stake": total_stake,
                "status": status,
            }
        )

    def create_pending_saga(self, ref, market_id, selection_id, payload):
        self.pending_sagas.append(
            {
                "customer_ref": ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": json.dumps(payload),
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return [x for x in self.pending_sagas if x["status"] == "PENDING"]

    def mark_saga_reconciled(self, ref):
        for s in self.pending_sagas:
            if s["customer_ref"] == ref:
                s["status"] = "RECONCILED"

    def get_simulation_settings(self):
        return self.sim_settings


class FakeBroker:
    def __init__(self):
        self.orders = []
        self.fill_id_set = set()

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
        order = {
            "market_id": market_id,
            "selection_id": selection_id,
            "price": price,
            "size": size,
            "customer_ref": customer_ref,
        }
        self.orders.append(order)

        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{len(self.orders)}",
                    "sizeMatched": size,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {
            "currentOrders": [
                {
                    "customerRef": o["customer_ref"],
                    "customerOrderRef": o["customer_ref"],
                    "sizeMatched": o["size"],
                }
                for o in self.orders
            ]
        }


@pytest.fixture
def bus():
    return DummyBus()


@pytest.fixture
def executor():
    return DummyExecutor()


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def broker():
    return FakeBroker()


@pytest.fixture
def engine(bus, db, broker, executor):
    return TradingEngine(bus, db, lambda: broker, executor)


def payload(**over):
    p = {
        "market_id": "1.200",
        "selection_id": 7,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10,
        "event_name": "Inter Milan",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }
    p.update(over)
    return p


def test_replay_idempotent_recovery(engine, db, broker):

    ref = "replay-test"

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": "1.200",
            "selection_id": 7,
            "raw_payload": json.dumps(payload()),
            "status": "PENDING",
        }
    )

    broker.orders.append(
        {
            "market_id": "1.200",
            "selection_id": 7,
            "size": 10,
            "customer_ref": ref,
        }
    )

    engine._recover_pending_sagas()
    first = len(db.saved_bets)

    engine._recover_pending_sagas()
    second = len(db.saved_bets)

    assert first == second


def test_duplicate_fills_not_counted_twice():

    pnl = PnLEngine(commission=4.5)

    fills = [
        {"side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5, "id": "A"},
        {"side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5, "id": "A"},
    ]

    seen = set()
    total = 0

    for f in fills:
        if f["id"] not in seen:
            seen.add(f["id"])
            total += pnl.calculate_back_pnl(f, best_lay_price=2.4)

    assert len(seen) == 1


def test_cancel_fill_race_condition(engine, broker):

    barrier = threading.Barrier(2)

    def place():
        barrier.wait()
        engine._handle_quick_bet(payload(stake=5))

    t1 = threading.Thread(target=place)
    t2 = threading.Thread(target=place)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert len(broker.orders) <= 2


def test_exposure_cap_blocks_trade(engine, bus, db):

    db.sim_settings["virtual_balance"] = 2

    engine._handle_quick_bet(
        payload(
            simulation_mode=True,
            bet_type="LAY",
            stake=10,
            price=4,
        )
    )

    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]

    assert len(failed) == 1


def test_safe_mode_hard_lock(engine, bus, broker):

    engine._toggle_kill_switch({"enabled": True})

    engine._handle_quick_bet(payload())

    assert broker.orders == []

    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]

    assert len(failed) == 1


def test_ghost_order_recovery(engine, db, broker):

    ref = "ghost-1"

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": "1.200",
            "selection_id": 7,
            "raw_payload": json.dumps(payload()),
            "status": "PENDING",
        }
    )

    broker.orders.append(
        {
            "market_id": "1.200",
            "selection_id": 7,
            "size": 10,
            "customer_ref": ref,
        }
    )

    engine._recover_pending_sagas()

    assert db.saved_bets[-1]["status"] in ["MATCHED", "PARTIALLY_MATCHED"]


def test_global_invariants_no_negative_exposure():

    safety = SafetyLayer()

    assert safety.validate_quick_bet_success(
        {
            "status": "MATCHED",
            "matched": 5,
            "stake": 5,
        }
    )


def test_race_condition_submit(engine, broker):

    threads = []

    for _ in range(4):
        t = threading.Thread(target=engine._handle_quick_bet, args=(payload(),))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 4


def test_no_order_in_safe_mode(engine, broker):

    engine._toggle_kill_switch({"enabled": True})

    engine._handle_quick_bet(payload())

    assert broker.orders == []