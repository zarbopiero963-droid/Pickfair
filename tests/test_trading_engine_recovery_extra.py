from core.trading_engine import TradingEngine


class DummyBus:
    def subscribe(self, *_args, **_kwargs):
        return None

    def publish(self, *_args, **_kwargs):
        return None


class DummyDB:
    def __init__(self):
        self.reconciled = []
        self.failed = []
        self.saved_bets = []

    def get_pending_sagas(self):
        return [
            {
                "customer_ref": "ref1",
                "market_id": "1.100",
                "selection_id": "10",
                "raw_payload": '{"stake": 10.0, "price": 2.0, "bet_type": "BACK", "runner_name": "Juve", "event_name": "Juve - Milan", "market_name": "Match Odds", "selection_id": 10}',
            }
        ]

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)

    def save_bet(self, *args, **kwargs):
        self.saved_bets.append((args, kwargs))

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyClient:
    def get_current_orders(self, *args, **kwargs):
        return {
            "currentOrders": [
                {
                    "customerOrderRef": "ref1",
                    "marketId": "1.100",
                    "sizeMatched": 10.0,
                    "price": 2.0,
                    "sizeRemaining": 0.0,
                }
            ],
            "matched": [],
            "unmatched": [],
        }


def test_trading_engine_recovery_of_pending_saga():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()

    engine = TradingEngine(bus, db, lambda: client, executor)
    engine._recover_pending_sagas()

    assert db.reconciled == ["ref1"]
    assert db.failed == []
    assert len(db.saved_bets) == 1