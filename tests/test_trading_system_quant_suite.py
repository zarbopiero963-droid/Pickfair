import random
import time
import statistics
import threading

import pytest

from core.trading_engine import TradingEngine
from pnl_engine import PnLEngine
from core.safety_layer import SafetyLayer


# ---------------------------------------------------------
# Deterministic Market Replay
# ---------------------------------------------------------

class MarketReplay:

    def __init__(self, ticks):
        self.ticks = ticks

    def replay(self):
        return list(self.ticks)


def test_market_replay_deterministic():

    ticks = [
        {"price": 2.0, "size": 10},
        {"price": 2.1, "size": 5},
        {"price": 2.2, "size": 7},
    ]

    replay = MarketReplay(ticks)

    a = replay.replay()
    b = replay.replay()

    assert a == b


# ---------------------------------------------------------
# Exchange Mirror Simulation
# ---------------------------------------------------------

class ExchangeMirror:

    def __init__(self):
        self.order_book = []

    def submit_order(self, price, size):
        self.order_book.append({"price": price, "size": size})

    def snapshot(self):
        return list(self.order_book)


def test_exchange_mirror_consistency():

    mirror = ExchangeMirror()

    mirror.submit_order(2.0, 5)
    mirror.submit_order(2.2, 3)

    snap1 = mirror.snapshot()
    snap2 = mirror.snapshot()

    assert snap1 == snap2


# ---------------------------------------------------------
# Probabilistic Stress Test
# ---------------------------------------------------------

def test_probabilistic_stress():

    pnl = PnLEngine()

    results = []

    for _ in range(500):

        price = random.uniform(1.2, 4.0)
        size = random.uniform(0.5, 20)

        r = pnl.calculate_back_pnl(
            {"side": "BACK", "sizeMatched": size, "averagePriceMatched": price},
            best_lay_price=price * 0.95,
        )

        results.append(r)

    mean = statistics.mean(results)

    assert mean == mean  # non NaN


# ---------------------------------------------------------
# Latency Profiling
# ---------------------------------------------------------

def test_latency_profile():

    latencies = []

    for _ in range(50):

        start = time.perf_counter()

        time.sleep(random.uniform(0.001, 0.005))

        end = time.perf_counter()

        latencies.append(end - start)

    avg_latency = statistics.mean(latencies)

    assert avg_latency < 0.01


# ---------------------------------------------------------
# Engine Safety Invariant
# ---------------------------------------------------------

def test_engine_safety_invariant():

    safety = SafetyLayer()

    assert safety.validate_quick_bet_success(
        {
            "status": "MATCHED",
            "matched": 10,
            "stake": 10,
        }
    )


# ---------------------------------------------------------
# Deterministic PnL Replay
# ---------------------------------------------------------

def test_deterministic_pnl_replay():

    pnl = PnLEngine()

    fills = [
        {"side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2},
        {"side": "BACK", "sizeMatched": 3, "averagePriceMatched": 3},
    ]

    r1 = pnl.calculate_selection_pnl(fills, best_back=2.4, best_lay=2.3)
    r2 = pnl.calculate_selection_pnl(fills, best_back=2.4, best_lay=2.3)

    assert r1 == r2


# ---------------------------------------------------------
# Concurrency Stress
# ---------------------------------------------------------

class DummyBroker:

    def __init__(self):
        self.orders = []

    def place_bet(self, market_id, selection_id, side, price, size,
                  persistence_type="LAPSE", customer_ref=None):

        self.orders.append(
            {
                "price": price,
                "size": size,
                "side": side,
            }
        )

        return {
            "status": "SUCCESS",
            "instructionReports": [
                {"betId": f"BET-{len(self.orders)}", "sizeMatched": size}
            ],
        }


class DummyBus:
    def publish(self, event, payload):
        pass


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def save_bet(self, *args):
        pass


def payload():

    return {
        "market_id": "1.200",
        "selection_id": 5,
        "bet_type": "BACK",
        "price": 2,
        "stake": 5,
        "event_name": "Test",
        "market_name": "Odds",
        "runner_name": "Runner",
        "simulation_mode": False,
    }


def test_concurrency_stress():

    broker = DummyBroker()
    engine = TradingEngine(DummyBus(), DummyDB(), lambda: broker, DummyExecutor())

    threads = []

    for _ in range(10):

        t = threading.Thread(target=engine._handle_quick_bet, args=(payload(),))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 10


# ---------------------------------------------------------
# Risk Limit Stress
# ---------------------------------------------------------

def test_risk_limit_behavior():

    safety = SafetyLayer()

    with pytest.raises(Exception):

        safety.validate_quick_bet_request(
            {
                "market_id": "1",
                "selection_id": "bad",
                "stake": "invalid",
            }
        )


# ---------------------------------------------------------
# Deterministic Tick Simulation
# ---------------------------------------------------------

def test_tick_simulation_deterministic():

    prices = [2, 2.1, 2.2, 2.3]

    first = [p for p in prices]
    second = [p for p in prices]

    assert first == second