import importlib
import sys
import types

from core.trading_engine import TradingEngine


def _install_telethon_stub():
    if "telethon" not in sys.modules:
        telethon_mod = types.ModuleType("telethon")
        telethon_mod.TelegramClient = object
        telethon_mod.events = object()
        sys.modules["telethon"] = telethon_mod

    if "telethon.sessions" not in sys.modules:
        sessions_mod = types.ModuleType("telethon.sessions")

        class DummyStringSession:
            def __init__(self, *args, **kwargs):
                pass

        sessions_mod.StringSession = DummyStringSession
        sys.modules["telethon.sessions"] = sessions_mod


_install_telethon_stub()

listener_mod = importlib.import_module("telegram_listener")
parse_signal_message = listener_mod.parse_signal_message
SignalQueue = listener_mod.SignalQueue


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
                    "betId": f"BET-{selection_id}-{len(self.place_bet_calls)}",
                    "sizeMatched": float(size),
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def test_e2e_multiple_telegram_signals_queue_flow_fifo_processing():
    messages = [
        """
        MASTER SIGNAL
        event_name: Juve - Milan
        market_name: Match Odds
        selection: Juve
        action: BACK
        master_price: 2.10
        market_id: 1.101
        selection_id: 11
        """,
        """
        MASTER SIGNAL
        event_name: Inter - Roma
        market_name: Match Odds
        selection: Inter
        action: BACK
        master_price: 2.30
        market_id: 1.202
        selection_id: 22
        """,
        """
        MASTER SIGNAL
        event_name: Napoli - Lazio
        market_name: Match Odds
        selection: Napoli
        action: BACK
        master_price: 1.95
        market_id: 1.303
        selection_id: 33
        """,
    ]

    parsed = [parse_signal_message(msg) for msg in messages]

    assert all(item is not None for item in parsed)

    queue = SignalQueue(maxsize=10)
    for item in parsed:
        queue.push(item)

    ordered = [queue.pop(), queue.pop(), queue.pop()]

    assert ordered[0]["market_id"] == "1.101"
    assert ordered[1]["market_id"] == "1.202"
    assert ordered[2]["market_id"] == "1.303"

    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    for item in ordered:
        payload = {
            "market_id": item["market_id"],
            "selection_id": item["selection_id"],
            "bet_type": item["side"],
            "price": float(item["price"]),
            "stake": 10.0,
            "event_name": item["event_name"],
            "market_name": item["market_name"],
            "runner_name": item["selection"],
            "simulation_mode": False,
        }
        engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 3
    assert len(db.saved_bets) == 3
    assert len(db.reconciled) == 3
    assert db.failed == []

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 3
    assert success[0][1]["market_id"] == "1.101"
    assert success[1][1]["market_id"] == "1.202"
    assert success[2][1]["market_id"] == "1.303"