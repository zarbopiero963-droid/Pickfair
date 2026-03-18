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


class HappyMicroClient:
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
            "instructionReports": [{"betId": "BET-123", "sizeMatched": 0.0}],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {"market_id": market_id, "instructions": instructions}
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {"market_id": market_id, "instructions": instructions}
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "BET-123", "sizeMatched": 0.5}],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = HappyMicroClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())
    return engine, bus, db, client


def test_microstake_boundary_values_are_detected_correctly():
    engine, _, _, _ = _make_engine()

    assert engine._needs_micro_stake(0.05) is False
    assert engine._needs_micro_stake(0.10) is True
    assert engine._needs_micro_stake(1.99) is True
    assert engine._needs_micro_stake(2.00) is False


def test_microstake_success_payload_has_expected_flags_and_status():
    engine, bus, db, client = _make_engine()

    payload = {
        "market_id": "1.500",
        "selection_id": 50,
        "bet_type": "BACK",
        "price": 2.3,
        "stake": 0.5,
        "event_name": "A - B",
        "market_name": "Match Odds",
        "runner_name": "Runner X",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1

    evt = success[0][1]
    assert evt["micro"] is True
    assert evt["sim"] is False
    assert evt["market_id"] == "1.500"
    assert evt["selection_id"] == 50
    assert evt["bet_type"] == "BACK"
    assert evt["runner_name"] == "Runner X"
    assert evt["status"] in {"PARTIALLY_MATCHED", "MATCHED", "UNMATCHED"}

    assert len(db.saved_bets) == 1
    assert db.saved_bets[0]["market_id"] == "1.500"


def test_microstake_creates_pending_saga_before_resolution():
    engine, _, db, _ = _make_engine()

    payload = {
        "market_id": "1.501",
        "selection_id": 51,
        "bet_type": "LAY",
        "price": 4.0,
        "stake": 1.0,
        "event_name": "C - D",
        "market_name": "Match Odds",
        "runner_name": "Runner Y",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(db.pending_sagas) == 1
    assert len(db.reconciled) == 1
    assert db.failed == []


def test_microstake_stub_prices_follow_side_convention():
    engine, _, _, _ = _make_engine()

    assert engine._micro_stub_price("BACK") == 1.01
    assert engine._micro_stub_price("LAY") == 1000.0