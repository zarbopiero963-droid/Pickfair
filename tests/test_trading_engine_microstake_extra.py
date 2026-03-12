from core.trading_engine import TradingEngine


class DummyBus:
    def __init__(self):
        self.events = []

    def subscribe(self, *_args, **_kwargs):
        return None

    def publish(self, name, payload):
        self.events.append((name, payload))


class DummyDB:
    def __init__(self):
        self.saved_bets = []
        self.pending = []

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": payload,
            }
        )

    def mark_saga_reconciled(self, _customer_ref):
        return None

    def mark_saga_failed(self, _customer_ref):
        return None

    def save_bet(self, *args, **kwargs):
        self.saved_bets.append((args, kwargs))

    def get_pending_sagas(self):
        return []

    def get_simulation_settings(self):
        return {"virtual_balance": 1000.0, "starting_balance": 1000.0, "bet_count": 0}

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, _new_balance):
        return None

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyClient:
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
                    "betId": "BET123",
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
                    "betId": "BET123",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: client, executor)
    return engine, bus, db, client


def test_trading_engine_microstake_full_flow():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.555",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.12,
        "stake": 0.5,
        "event_name": "Inter - Roma",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert client.place_bet_calls[0]["price"] == 1.01
    assert client.place_bet_calls[0]["size"] == 2.0

    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1

    success = [x for x in bus.events if x[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is True