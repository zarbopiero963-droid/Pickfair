import pytest

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
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []
        self.reconciled = []
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
        self.reconciled.append(customer_ref)

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


class CancelFailClient:
    def __init__(self):
        self.place_bet_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []

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
        self.place_bet_calls.append((market_id, selection_id, side, price, size, customer_ref))
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "BET-1", "sizeMatched": 0.0}],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append((market_id, instructions))
        return {"status": "FAILURE", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append((market_id, instructions))
        return {"status": "SUCCESS", "instructionReports": []}

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class ReplaceFailClient:
    def __init__(self):
        self.place_bet_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []

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
        self.place_bet_calls.append((market_id, selection_id, side, price, size, customer_ref))
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "BET-2", "sizeMatched": 0.0}],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append((market_id, instructions))
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append((market_id, instructions))
        return {"status": "FAILURE", "instructionReports": []}

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_engine(client):
    bus = DummyBus()
    db = DummyDB()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())
    return engine, bus, db


def test_execute_micro_stake_rejects_too_small_requested_stake():
    engine, _, _ = _make_engine(CancelFailClient())

    with pytest.raises(ValueError, match="Stake micro troppo basso"):
        engine._execute_micro_stake(
            client=CancelFailClient(),
            market_id="1.100",
            selection_id=11,
            side="BACK",
            price=2.0,
            stake=0.05,
            customer_ref="REF-1",
        )


def test_execute_micro_stake_cancel_failure_raises_runtime_error():
    client = CancelFailClient()
    engine, _, _ = _make_engine(client)

    with pytest.raises(RuntimeError, match="Micro-stake step CANCEL fallito"):
        engine._execute_micro_stake(
            client=client,
            market_id="1.200",
            selection_id=12,
            side="BACK",
            price=2.5,
            stake=0.5,
            customer_ref="REF-2",
        )

    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 0


def test_execute_micro_stake_replace_failure_triggers_rollback_cancel():
    client = ReplaceFailClient()
    engine, _, _ = _make_engine(client)

    with pytest.raises(RuntimeError, match="Micro-stake step REPLACE fallito"):
        engine._execute_micro_stake(
            client=client,
            market_id="1.300",
            selection_id=13,
            side="LAY",
            price=3.2,
            stake=1.0,
            customer_ref="REF-3",
        )

    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) == 2
    assert len(client.replace_orders_calls) == 1


def test_micro_helpers_build_expected_instruction_shapes():
    engine, _, _ = _make_engine(CancelFailClient())

    limit_ins = engine._build_limit_instruction(11, "back", 2.5, 2.0)
    cancel_ins = engine._build_cancel_instruction("BET-99", size_reduction=1.5)
    replace_ins = engine._build_replace_instruction("BET-99", 3.1)

    assert limit_ins["selectionId"] == 11
    assert limit_ins["side"] == "BACK"
    assert limit_ins["limitOrder"]["size"] == 2.0
    assert limit_ins["limitOrder"]["price"] == 2.5

    assert cancel_ins["betId"] == "BET-99"
    assert cancel_ins["sizeReduction"] == 1.5

    assert replace_ins["betId"] == "BET-99"
    assert replace_ins["newPrice"] == 3.1