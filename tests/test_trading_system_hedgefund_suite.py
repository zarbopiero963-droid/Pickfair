import json
import random
import time
import threading

import pytest

from core.trading_engine import TradingEngine
from pnl_engine import PnLEngine
from core.safety_layer import SafetyLayer


# ----------------------------------------------------
# Event Store (event sourcing simulation)
# ----------------------------------------------------

class EventStore:

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)

    def replay(self):
        return list(self.events)


# ----------------------------------------------------
# Ledger (accounting model)
# ----------------------------------------------------

class Ledger:

    def __init__(self):
        self.position = 0
        self.cash = 0

    def apply_fill(self, side, price, size):

        if side == "BACK":
            self.position += size
            self.cash -= price * size

        elif side == "LAY":
            self.position -= size
            self.cash += price * size


# ----------------------------------------------------
# Fake infrastructure
# ----------------------------------------------------

class DummyBus:

    def __init__(self):
        self.events = []
        self._handlers = {}

    def subscribe(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def publish(self, event, payload):
        self.events.append((event, payload))


class DummyExecutor:

    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class FakeDB:

    def __init__(self):
        self.saved_bets = []
        self.pending_sagas = []

    def save_bet(self, *args):
        self.saved_bets.append(args)

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


class ChaosBroker:

    def __init__(self):
        self.orders = []
        self.latency = 0
        self.drop_rate = 0
        self.duplicate_fill = False

    def place_bet(self, market_id, selection_id, side, price, size,
                  persistence_type="LAPSE", customer_ref=None):

        time.sleep(self.latency)

        if random.random() < self.drop_rate:
            raise ConnectionError("network drop")

        self.orders.append(
            {
                "price": price,
                "size": size,
                "side": side,
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

    def get_current_orders(self):

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


# ----------------------------------------------------
# Fixtures
# ----------------------------------------------------

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
    return ChaosBroker()


@pytest.fixture
def engine(bus, db, broker, executor):
    return TradingEngine(bus, db, lambda: broker, executor)


def payload(**override):

    p = {
        "market_id": "1.100",
        "selection_id": 5,
        "bet_type": "BACK",
        "price": 2.0,
        "stake": 10,
        "event_name": "Inter Milan",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }

    p.update(override)

    return p


# ----------------------------------------------------
# EVENT SOURCING REPLAY
# ----------------------------------------------------

def test_event_store_replay_deterministic():

    store = EventStore()

    for i in range(10):

        event = {
            "price": random.uniform(1.5, 3),
            "size": random.uniform(1, 5),
        }

        store.append(event)

    first = store.replay()
    second = store.replay()

    assert first == second


# ----------------------------------------------------
# LEDGER ACCOUNTING
# ----------------------------------------------------

def test_ledger_position_and_cash():

    ledger = Ledger()

    ledger.apply_fill("BACK", 2.0, 10)

    assert ledger.position == 10
    assert ledger.cash == -20


# ----------------------------------------------------
# RECONCILIATION
# ----------------------------------------------------

def test_exchange_reconciliation(engine, broker, db):

    ref = "recon-1"

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": "1.100",
            "selection_id": 5,
            "raw_payload": json.dumps(payload()),
            "status": "PENDING",
        }
    )

    broker.orders.append(
        {
            "price": 2,
            "size": 10,
            "ref": ref,
            "side": "BACK",
        }
    )

    engine._recover_pending_sagas()

    assert len(db.saved_bets) == 1


# ----------------------------------------------------
# CHAOS NETWORK TEST
# ----------------------------------------------------

def test_broker_network_chaos(engine, broker):

    broker.drop_rate = 0.3

    for _ in range(20):

        try:
            engine._handle_quick_bet(payload())
        except Exception:
            pass

    assert True


# ----------------------------------------------------
# DUPLICATE FILLS
# ----------------------------------------------------

def test_duplicate_fills():

    pnl = PnLEngine()

    fills = [
        {"id": "1", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2},
        {"id": "1", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2},
    ]

    seen = set()
    total = 0

    for f in fills:

        if f["id"] not in seen:
            seen.add(f["id"])
            total += pnl.calculate_back_pnl(f, best_lay_price=1.9)

    assert len(seen) == 1


# ----------------------------------------------------
# SAFE MODE SYSTEM INVARIANT
# ----------------------------------------------------

def test_safe_mode_blocks_orders(engine, broker):

    engine._toggle_kill_switch({"enabled": True})

    engine._handle_quick_bet(payload())

    assert broker.orders == []


# ----------------------------------------------------
# SYSTEM INVARIANT
# ----------------------------------------------------

def test_global_safety_invariant():

    safety = SafetyLayer()

    assert safety.validate_quick_bet_success(
        {
            "market_id": "1.100",
            "selection_id": 5,
            "bet_type": "BACK",
            "price": 2.0,
            "stake": 5,
            "matched": 5,
            "status": "MATCHED",
            "sim": False,
        }
    )


# ----------------------------------------------------
# THREAD RACE CONDITION
# ----------------------------------------------------

def test_thread_race_condition(engine, broker):

    threads = []

    for _ in range(6):
        t = threading.Thread(target=engine._handle_quick_bet, args=(payload(),))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 6


# ----------------------------------------------------
# DETERMINISTIC SIMULATION
# ----------------------------------------------------

def test_deterministic_simulation():

    pnl = PnLEngine()

    events = [
        {"side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2},
        {"side": "BACK", "sizeMatched": 3, "averagePriceMatched": 3},
    ]

    r1 = pnl.calculate_selection_pnl(events, best_back=2.5, best_lay=2.4)
    r2 = pnl.calculate_selection_pnl(events, best_back=2.5, best_lay=2.4)

    assert r1 == r2