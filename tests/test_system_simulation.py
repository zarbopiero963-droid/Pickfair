from concurrent.futures import ThreadPoolExecutor, as_completed

from core.trading_engine import TradingEngine
from simulation_broker import SimulationBroker


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def subscribe(self, event_name, callback):
        self.subscribers.setdefault(event_name, []).append(callback)

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))
        for callback in self.subscribers.get(event_name, []):
            callback(payload)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending = []
        self.bets = []
        self.cashouts = []
        self.sim_settings = {"virtual_balance": 10000.0, "bet_count": 0}

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": "{}",
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return [p for p in self.pending if p["status"] == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        for row in self.pending:
            if row["customer_ref"] == customer_ref:
                row["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        for row in self.pending:
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
        self.bets.append(
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

    def save_cashout_transaction(
        self,
        market_id,
        selection_id,
        original_bet_id,
        cashout_bet_id,
        original_side,
        original_stake,
        original_price,
        cashout_side,
        cashout_stake,
        cashout_price,
        profit_loss,
    ):
        self.cashouts.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "cashout_bet_id": cashout_bet_id,
                "cashout_side": cashout_side,
                "cashout_stake": cashout_stake,
                "cashout_price": cashout_price,
                "profit_loss": profit_loss,
            }
        )

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def increment_simulation_bet_count(self, new_balance):
        self.sim_settings["virtual_balance"] = float(new_balance)
        self.sim_settings["bet_count"] = int(self.sim_settings.get("bet_count", 0)) + 1

    def save_simulation_bet(self, **kwargs):
        self.bets.append({"sim": True, **kwargs})


class DummyClient:
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
        size_matched = 0.0 if float(size) == 2.0 else float(size)
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{customer_ref or 'X'}",
                    "sizeMatched": size_matched,
                }
            ],
        }

    def place_orders(self, market_id, instructions, customer_ref=None):
        reports = []
        for i, ins in enumerate(instructions or [], start=1):
            reports.append(
                {
                    "betId": f"BET-{customer_ref or 'X'}-{i}",
                    "sizeMatched": float(ins.get("limitOrder", {}).get("size", 0.0)),
                }
            )
        return {"status": "SUCCESS", "instructionReports": reports}

    def cancel_orders(self, market_id=None, instructions=None):
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        bet_id = instructions[0].get("betId", "") if instructions else ""
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": bet_id or "BET-REPLACED", "sizeMatched": 0.5}],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}

    def get_market_book(self, market_id):
        return {
            "runners": [
                {
                    "selectionId": 1,
                    "ex": {
                        "availableToBack": [{"price": 2.0, "size": 500}],
                        "availableToLay": [{"price": 2.02, "size": 500}],
                    },
                },
                {
                    "selectionId": 2,
                    "ex": {
                        "availableToBack": [{"price": 3.0, "size": 500}],
                        "availableToLay": [{"price": 3.05, "size": 500}],
                    },
                },
            ]
        }


def test_simulation_broker_full_order_cancel_and_reset_cycle():
    broker = SimulationBroker(initial_balance=100.0)

    placed = broker.place_order(
        market_id="1.200",
        selection_id=10,
        side="BACK",
        price=2.0,
        size=10.0,
        runner_name="Runner A",
        partial_match_pct=0.4,
    )

    assert placed["status"] == "EXECUTABLE"
    assert placed["sizeMatched"] == 4.0
    assert placed["sizeRemaining"] == 6.0
    assert broker.get_balance() == 90.0

    cancelled = broker.cancel_order(placed["betId"])
    assert cancelled["success"] is True
    assert cancelled["sizeCancelled"] == 6.0
    assert cancelled["sizeMatched"] == 4.0
    assert broker.get_order(placed["betId"])["status"] == "EXECUTION_COMPLETE"
    assert broker.get_balance() == 96.0

    broker.reset()
    assert broker.get_balance() == 100.0
    assert broker.orders == {}
    assert broker.bet_counter == 0


def test_trading_engine_quick_bet_simulation_persists_runtime_state():
    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: DummyClient(), executor)

    payload = {
        "market_id": "1.100",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.10,
        "stake": 10.0,
        "event_name": "A - B",
        "market_name": "MATCH_ODDS",
        "runner_name": "Home",
        "simulation_mode": True,
    }

    engine._handle_quick_bet(payload)

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["sim"] is True
    assert success[0][1]["new_balance"] == 9990.0
    assert db.sim_settings["virtual_balance"] == 9990.0
    assert db.sim_settings["bet_count"] == 1
    assert db.bets[-1]["sim"] is True
    assert db.bets[-1]["status"] == "MATCHED"


def test_trading_engine_micro_stake_runtime_path():
    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.101",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.20,
        "stake": 0.50,
        "event_name": "C - D",
        "market_name": "MATCH_ODDS",
        "runner_name": "Away",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is True
    assert len(db.pending) == 1
    assert db.pending[0]["status"] == "RECONCILED"
    assert db.bets[-1]["status"] in {"UNMATCHED", "PARTIALLY_MATCHED", "MATCHED"}


def test_trading_engine_dutching_and_cashout_runtime_flow():
    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, executor)

    dutching_payload = {
        "market_id": "1.102",
        "market_type": "MATCH_ODDS",
        "event_name": "E - F",
        "market_name": "MATCH_ODDS",
        "bet_type": "BACK",
        "total_stake": 25.0,
        "results": [
            {"selectionId": 1, "runnerName": "One", "price": 2.0, "stake": 10.0},
            {"selectionId": 2, "runnerName": "Two", "price": 3.0, "stake": 15.0},
        ],
        "simulation_mode": False,
        "use_best_price": False,
    }

    engine._handle_place_dutching(dutching_payload)

    dutching_success = [evt for evt in bus.events if evt[0] == "DUTCHING_SUCCESS"]
    assert len(dutching_success) == 1
    assert dutching_success[0][1]["matched"] == 25.0
    assert db.bets[-1]["status"] == "MATCHED"

    cashout_payload = {
        "market_id": "1.103",
        "selection_id": 1,
        "side": "LAY",
        "stake": 5.0,
        "price": 1.80,
        "green_up": 2.50,
    }

    engine._handle_cashout(cashout_payload)

    cashout_success = [evt for evt in bus.events if evt[0] == "CASHOUT_SUCCESS"]
    assert len(cashout_success) == 1
    assert cashout_success[0][1]["status"] == "MATCHED"
    assert len(db.cashouts) == 1
    assert db.cashouts[0]["profit_loss"] == 2.50


def test_stress_200_parallel_dutching_math_runs_consistently():
    from dutching import calculate_dutching_stakes

    def worker(i: int):
        selections = [
            {"selectionId": 1, "runnerName": f"A{i}", "price": 2.0},
            {"selectionId": 2, "runnerName": f"B{i}", "price": 3.0},
        ]
        result, profit, book = calculate_dutching_stakes(
            selections=selections,
            total_stake=100.0,
            bet_type="BACK",
            commission=4.5,
        )
        return len(result), round(sum(float(r["stake"]) for r in result), 2), profit, book

    futures = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i in range(200):
            futures.append(ex.submit(worker, i))

        completed = 0
        for fut in as_completed(futures):
            rows, total, profit, book = fut.result()
            assert rows == 2
            assert total == 100.0
            assert isinstance(profit, float)
            assert isinstance(book, float)
            completed += 1

    assert completed == 200