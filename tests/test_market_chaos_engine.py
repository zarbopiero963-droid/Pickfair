import time

from core.trading_engine import TradingEngine


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def subscribe(self, name, fn):
        self.subscribers[name] = fn

    def publish(self, name, payload):
        self.events.append((name, payload))
        if name in self.subscribers:
            self.subscribers[name](payload)


class DummyDB:
    def __init__(self):
        self.pending = []
        self.saved_bets = []
        self.saved_cashouts = []
        self.reconciled = []
        self.failed = []
        self.sim_bets = []
        self.sim_balance = 1000.0
        self.bet_count = 0

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": payload,
            }
        )

    def get_pending_sagas(self):
        return list(self.pending)

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)
        for row in self.pending:
            if row["customer_ref"] == customer_ref:
                row["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)
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
        status="PENDING",
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
        return {
            "virtual_balance": self.sim_balance,
            "starting_balance": 1000.0,
            "bet_count": self.bet_count,
        }

    def save_simulation_bet(self, **kwargs):
        self.sim_bets.append(kwargs)

    def increment_simulation_bet_count(self, new_balance):
        self.sim_balance = float(new_balance)
        self.bet_count += 1


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class ChaosClient:
    def __init__(self):
        self.place_bet_calls = []
        self.place_orders_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.current_orders_response = {"currentOrders": [], "matched": [], "unmatched": []}

        self.fail_place = False
        self.fail_place_exception = None
        self.fail_cancel = False
        self.fail_replace = False
        self.place_status = "SUCCESS"
        self.cancel_status = "SUCCESS"
        self.replace_status = "SUCCESS"

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

        if self.fail_place_exception is not None:
            raise self.fail_place_exception

        if self.fail_place:
            return {"status": "FAILURE", "instructionReports": []}

        return {
            "status": self.place_status,
            "instructionReports": [
                {
                    "betId": "BET123",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def place_orders(self, market_id=None, instructions=None, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
                "customer_ref": customer_ref,
            }
        )

        if self.fail_place_exception is not None:
            raise self.fail_place_exception

        reports = []
        for idx, instr in enumerate(instructions or [], start=1):
            reports.append(
                {
                    "betId": f"ORD{idx}",
                    "sizeMatched": 0.0,
                    "selectionId": instr.get("selectionId"),
                }
            )

        return {
            "status": self.place_status,
            "instructionReports": reports,
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
            }
        )
        if self.fail_cancel:
            return {"status": "FAILURE", "instructionReports": []}
        return {"status": self.cancel_status, "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
            }
        )
        if self.fail_replace:
            return {"status": "FAILURE", "instructionReports": []}
        return {
            "status": self.replace_status,
            "instructionReports": [
                {
                    "betId": "BET123",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return self.current_orders_response

    def get_market_book(self, market_id):
        return {
            "marketId": market_id,
            "runners": [
                {
                    "selectionId": 1,
                    "ex": {
                        "availableToBack": [{"price": 2.0, "size": 1000.0}],
                        "availableToLay": [{"price": 2.02, "size": 1000.0}],
                    },
                },
                {
                    "selectionId": 2,
                    "ex": {
                        "availableToBack": [{"price": 3.0, "size": 1000.0}],
                        "availableToLay": [{"price": 3.05, "size": 1000.0}],
                    },
                },
            ],
        }


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = ChaosClient()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: client, executor)
    return engine, bus, db, client


def test_chaos_safe_mode_blocks_quick_bet():
    engine, bus, db, client = _make_engine()
    engine._toggle_kill_switch(True)

    engine._handle_quick_bet(
        {
            "market_id": "1.1",
            "selection_id": 11,
            "bet_type": "BACK",
            "price": 2.0,
            "stake": 10.0,
            "runner_name": "Juve",
            "simulation_mode": False,
        }
    )

    assert client.place_bet_calls == []
    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert "SAFE MODE" in failed[0][1]


def test_chaos_microstake_rollback_on_replace_failure():
    engine, bus, db, client = _make_engine()
    client.fail_replace = True

    engine._handle_quick_bet(
        {
            "market_id": "1.2",
            "selection_id": 22,
            "bet_type": "BACK",
            "price": 2.20,
            "stake": 0.50,
            "runner_name": "Inter",
            "event_name": "Inter - Roma",
            "market_name": "Match Odds",
            "simulation_mode": False,
        }
    )

    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) >= 2
    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert db.saved_bets[-1]["status"] == "FAILED"


def test_chaos_recovery_after_network_exception():
    engine, bus, db, client = _make_engine()

    class NetworkBoom(Exception):
        pass

    client.fail_place_exception = NetworkBoom("network down")
    client.current_orders_response = {
        "currentOrders": [
            {
                "customerOrderRef": None,
                "customerRef": None,
                "marketId": "1.3",
                "sizeMatched": 0.0,
            }
        ],
        "matched": [],
        "unmatched": [],
    }

    original_reconcile = engine._reconcile_orders

    def fake_reconcile(_client, market_id, customer_ref, known_bet_ids=None):
        return (
            True,
            [
                {
                    "customerOrderRef": customer_ref,
                    "marketId": market_id,
                    "sizeMatched": 10.0,
                    "price": 2.5,
                    "sizeRemaining": 0.0,
                }
            ],
        )

    engine._reconcile_orders = fake_reconcile

    try:
        engine._handle_quick_bet(
            {
                "market_id": "1.3",
                "selection_id": 33,
                "bet_type": "BACK",
                "price": 2.5,
                "stake": 10.0,
                "runner_name": "Milan",
                "event_name": "Milan - Napoli",
                "market_name": "Match Odds",
                "simulation_mode": False,
            }
        )
    finally:
        engine._reconcile_orders = original_reconcile

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["recovered"] is True
    assert db.saved_bets[-1]["status"] == "MATCHED"


def test_chaos_recovery_pending_saga_marks_failed_when_missing():
    engine, bus, db, client = _make_engine()
    db.pending = [
        {
            "customer_ref": "ref_missing",
            "market_id": "1.4",
            "selection_id": "99",
            "raw_payload": '{"stake": 5.0}',
        }
    ]

    client.current_orders_response = {"currentOrders": [], "matched": [], "unmatched": []}
    engine._recover_pending_sagas()

    assert "ref_missing" in db.failed


def test_chaos_dutching_best_price_path_success():
    engine, bus, db, client = _make_engine()

    engine._handle_place_dutching(
        {
            "market_id": "1.5",
            "market_type": "MATCH_ODDS",
            "event_name": "Juve - Roma",
            "market_name": "Match Odds",
            "bet_type": "BACK",
            "total_stake": 20.0,
            "results": [
                {"selectionId": 1, "runnerName": "Juve", "price": 1.95, "stake": 10.0},
                {"selectionId": 2, "runnerName": "Roma", "price": 2.95, "stake": 10.0},
            ],
            "simulation_mode": False,
            "use_best_price": True,
        }
    )

    success = [e for e in bus.events if e[0] == "DUTCHING_SUCCESS"]
    assert len(success) == 1
    assert len(client.place_orders_calls) == 1
    assert db.saved_bets[-1]["status"] in ("UNMATCHED", "MATCHED", "PARTIALLY_MATCHED")


def test_chaos_cashout_simulation_like_real_success():
    engine, bus, db, client = _make_engine()

    engine._handle_cashout(
        {
            "market_id": "1.6",
            "selection_id": 10,
            "side": "LAY",
            "stake": 3.0,
            "price": 1.80,
            "green_up": 1.25,
        }
    )

    success = [e for e in bus.events if e[0] == "CASHOUT_SUCCESS"]
    assert len(success) == 1
    assert len(db.saved_cashouts) == 1


def test_chaos_microstake_stub_prices_back_and_lay():
    engine, _, _, _ = _make_engine()
    assert engine._micro_stub_price("BACK") == 1.01
    assert engine._micro_stub_price("LAY") == 1000.0


def test_chaos_stub_cleanup_detects_micro_orders():
    engine, _, _, client = _make_engine()

    recovered = [
        {
            "betId": "B1",
            "price": 1.01,
            "sizeRemaining": 2.0,
        },
        {
            "betId": "B2",
            "price": 1000.0,
            "sizeRemaining": 2.0,
        },
    ]

    ok, _cancelled = engine._cancel_stub_orders(client, "1.7", recovered)
    assert ok is True
    assert len(client.cancel_orders_calls) == 1


def test_chaos_compute_order_status_partial():
    engine, _, _, _ = _make_engine()
    assert engine._compute_order_status(5.0, 10.0) == "PARTIALLY_MATCHED"
    assert engine._compute_order_status(10.0, 10.0) == "MATCHED"
    assert engine._compute_order_status(0.0, 10.0) == "UNMATCHED"