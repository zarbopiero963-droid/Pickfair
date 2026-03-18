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
        self.failed = []
        self.reconciled = []
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


class MicroClient:
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
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{selection_id}",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [],
        }

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
                    "sizeMatched": 0.5,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = MicroClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())
    return engine, bus, db, client


def test_microstake_back_uses_stub_price_and_replace_flow():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.101",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.34,
        "stake": 0.5,
        "event_name": "A - B",
        "market_name": "Match Odds",
        "runner_name": "Runner A",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert client.place_bet_calls[0]["price"] == 1.01
    assert client.place_bet_calls[0]["size"] == 2.0

    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is True
    assert db.saved_bets[-1]["status"] in {"UNMATCHED", "PARTIALLY_MATCHED", "MATCHED"}


def test_microstake_lay_uses_opposite_stub_price():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.102",
        "selection_id": 12,
        "bet_type": "LAY",
        "price": 3.1,
        "stake": 1.0,
        "event_name": "C - D",
        "market_name": "Match Odds",
        "runner_name": "Runner B",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert client.place_bet_calls[0]["price"] == 1000.0
    assert client.place_bet_calls[0]["size"] == 2.0
    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is True


def test_non_microstake_path_does_not_use_stub_flow():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.103",
        "selection_id": 13,
        "bet_type": "BACK",
        "price": 2.2,
        "stake": 5.0,
        "event_name": "E - F",
        "market_name": "Match Odds",
        "runner_name": "Runner C",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert client.place_bet_calls[0]["price"] == 2.2
    assert client.place_bet_calls[0]["size"] == 5.0
    assert client.cancel_orders_calls == []
    assert client.replace_orders_calls == []

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is False


def test_microstake_path_creates_and_resolves_pending_saga():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.104",
        "selection_id": 14,
        "bet_type": "BACK",
        "price": 4.0,
        "stake": 0.25,
        "event_name": "G - H",
        "market_name": "Match Odds",
        "runner_name": "Runner D",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(db.pending_sagas) == 1
    assert len(db.reconciled) == 1
    assert db.failed == []