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
        self.saved_cashouts = []
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
        return None

    def mark_saga_failed(self, customer_ref):
        return None

    def save_bet(self, **kwargs):
        self.saved_bets.append(kwargs)

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, new_balance):
        self.sim_settings["virtual_balance"] = new_balance

    def save_cashout_transaction(self, **kwargs):
        self.saved_cashouts.append(kwargs)


class DummyClient:
    def __init__(self):
        self.place_bet_calls = []

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
                    "sizeMatched": float(size),
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def test_e2e_cashout_flow_runtime_success():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    payload = {
        "market_id": "1.700",
        "selection_id": 70,
        "side": "LAY",
        "stake": 5.0,
        "price": 1.80,
        "green_up": 2.50,
    }

    engine._handle_cashout(payload)

    assert len(client.place_bet_calls) == 1
    assert len(db.saved_cashouts) == 1

    row = db.saved_cashouts[0]
    assert row["market_id"] == "1.700"
    assert row["selection_id"] == 70
    assert row["cashout_side"] == "LAY"
    assert row["cashout_stake"] == 5.0
    assert row["cashout_price"] == 1.80
    assert row["profit_loss"] == 2.50

    success = [evt for evt in bus.events if evt[0] == "CASHOUT_SUCCESS"]
    assert len(success) == 1

    evt = success[0][1]
    assert evt["market_id"] == "1.700"
    assert evt["selection_id"] == 70
    assert evt["side"] == "LAY"
    assert evt["stake"] == 5.0
    assert evt["price"] == 1.80
    assert evt["green_up"] == 2.50
    assert evt["status"] == "MATCHED"