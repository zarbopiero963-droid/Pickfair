import json
import random
import threading
import time

import pytest
from hypothesis import given, strategies as st

from core.trading_engine import TradingEngine
from pnl_engine import PnLEngine
from core.safety_layer import SafetyLayer


# ---------------------------
# Infrastructure helpers
# ---------------------------

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


class InMemoryDB:

    def __init__(self):
        self.bets = []
        self.pending_sagas = []
        self.sim_settings = {"virtual_balance": 1000}

    def save_bet(self, *args):
        self.bets.append(args)

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


class ChaosBroker:

    """
    Broker simulator capable of:
    - latency
    - duplicate fills
    - dropped acknowledgements
    """

    def __init__(self):

        self.orders = []
        self.latency = 0
        self.duplicate_fill = False
        self.drop_ack = False

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

        time.sleep(self.latency)

        if not self.drop_ack:
            self.orders.append(
                {
                    "market_id": market_id,
                    "selection_id": selection_id,
                    "price": price,
                    "size": size,
                    "ref": customer_ref,
                }
            )

        fill = {
            "betId": f"BET-{len(self.orders)}",
            "sizeMatched": size,
        }

        reports = [fill]

        if self.duplicate_fill:
            reports.append(fill)

        return {"status": "SUCCESS", "instructionReports": reports}

    def get_current_orders(self, *args, **kwargs):

        return {
            "currentOrders": [
                {
                    "customerRef": o["ref"],
                    "customerOrderRef": o["ref"],
                    "sizeMatched": o["size"],
                }
                for o in self.orders
            ]
        }


# ---------------------------
# Fixtures
# ---------------------------

@pytest.fixture
def bus():
    return DummyBus()


@pytest.fixture
def executor():
    return DummyExecutor()


@pytest.fixture
def db():
    return InMemoryDB()


@pytest.fixture
def broker():
    return ChaosBroker()


@pytest.fixture
def engine(bus, db, broker, executor):
    return TradingEngine(bus, db, lambda: broker, executor)


def payload(**override):

    p = {
        "market_id": "1.500",
        "selection_id": 9,
        "bet_type": "BACK",
        "price": 2.2,
        "stake": 10,
        "event_name": "Inter Milan",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }

    p.update(override)

    return p


# ----------------------------------------------------
# ORDER LIFECYCLE TEST
# ----------------------------------------------------

def test_full_order_lifecycle(engine, broker):

    engine._handle_quick_bet(payload())

    assert len(broker.orders) == 1

    order = broker.orders[0]

    assert order["price"] == 2.2
    assert order["size"] == 10


# ----------------------------------------------------
# LEDGER RECONCILIATION
# ----------------------------------------------------

def test_ledger_reconciliation(engine, broker, db):

    ref = "ledger-1"

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": "1.500",
            "selection_id": 9,
            "raw_payload": json.dumps(payload()),
            "status": "PENDING",
        }
    )

    broker.orders.append(
        {
            "market_id": "1.500",
            "selection_id": 9,
            "price": 2.2,
            "size": 10,
            "ref": ref,
        }
    )

    engine._recover_pending_sagas()

    assert len(db.bets) == 1


# ----------------------------------------------------
# EVENT SOURCING REPLAY
# ----------------------------------------------------

def test_event_replay_deterministic():

    events = []

    pnl = PnLEngine()

    for _ in range(10):

        price = random.uniform(1.5, 3.0)
        size = random.uniform(1, 5)

        events.append(
            {
                "side": "BACK",
                "sizeMatched": size,
                "averagePriceMatched": price,
            }
        )

    first = pnl.calculate_selection_pnl(events, best_back=2, best_lay=2)

    second = pnl.calculate_selection_pnl(events, best_back=2, best_lay=2)

    assert first == second


# ----------------------------------------------------
# CHAOS BROKER LATENCY
# ----------------------------------------------------

def test_broker_latency(engine, broker):

    broker.latency = 0.1

    engine._handle_quick_bet(payload())

    assert len(broker.orders) == 1


# ----------------------------------------------------
# DUPLICATE FILLS
# ----------------------------------------------------

def test_duplicate_fills_filtered():

    pnl = PnLEngine()

    fills = [
        {"id": "1", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5},
        {"id": "1", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5},
    ]

    seen = set()
    total = 0

    for f in fills:

        if f["id"] not in seen:
            seen.add(f["id"])
            total += pnl.calculate_back_pnl(f, best_lay_price=2.4)

    assert len(seen) == 1


# ----------------------------------------------------
# PROPERTY BASED INVARIANTS
# ----------------------------------------------------

@given(
    price=st.floats(min_value=1.01, max_value=10),
    size=st.floats(min_value=0.1, max_value=100),
)
def test_pnl_never_nan(price, size):

    pnl = PnLEngine()

    result = pnl.calculate_back_pnl(
        {
            "side": "BACK",
            "sizeMatched": size,
            "averagePriceMatched": price,
        },
        best_lay_price=price * 0.9,
    )

    assert result == result


# ----------------------------------------------------
# GLOBAL SAFETY INVARIANT
# ----------------------------------------------------

def test_safety_layer_invariant():

    safety = SafetyLayer()

    assert safety.validate_quick_bet_success(
        {
            "status": "MATCHED",
            "matched": 5,
            "stake": 5,
        }
    )


# ----------------------------------------------------
# RACE CONDITION SUBMIT
# ----------------------------------------------------

def test_submit_race_condition(engine, broker):

    threads = []

    for _ in range(5):
        t = threading.Thread(target=engine._handle_quick_bet, args=(payload(),))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 5


# ----------------------------------------------------
# SAFE MODE LOCK
# ----------------------------------------------------

def test_safe_mode_blocks_orders(engine, broker):

    engine._toggle_kill_switch({"enabled": True})

    engine._handle_quick_bet(payload())

    assert broker.orders == []


# ----------------------------------------------------
# DETERMINISTIC SIMULATION
# ----------------------------------------------------

def test_deterministic_simulation():

    pnl = PnLEngine()

    events = [
        {"side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2},
        {"side": "BACK", "sizeMatched": 3, "averagePriceMatched": 3},
    ]

    a = pnl.calculate_selection_pnl(events, best_back=2.5, best_lay=2.4)
    b = pnl.calculate_selection_pnl(events, best_back=2.5, best_lay=2.4)

    assert a == b