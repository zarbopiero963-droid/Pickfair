import importlib
import sys
import types

from core.trading_engine import TradingEngine


def _install_stubs():
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

    if "customtkinter" not in sys.modules:
        ctk = types.ModuleType("customtkinter")
        ctk.CTkFrame = object
        ctk.CTkLabel = object
        ctk.CTkButton = object
        ctk.CTkEntry = object
        ctk.CTkCheckBox = object
        sys.modules["customtkinter"] = ctk

    if "tkinter" not in sys.modules:
        tk = types.ModuleType("tkinter")
        sys.modules["tkinter"] = tk
    else:
        tk = sys.modules["tkinter"]

    class DummyVar:
        def __init__(self, value=None):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    tk.StringVar = DummyVar
    tk.BooleanVar = DummyVar


_install_stubs()

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
            "instructionReports": [{"betId": f"BET-{selection_id}", "sizeMatched": float(size)}],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


def test_e2e_telegram_to_ui_to_order_flow():
    msg = """
    MASTER SIGNAL
    event_name: Juve - Milan
    market_name: Match Odds
    selection: Juve
    action: BACK
    master_price: 2.10
    market_id: 1.123
    selection_id: 11
    """

    parsed = parse_signal_message(msg)
    assert parsed is not None

    queue = SignalQueue(maxsize=5)
    queue.push(parsed)
    queued = queue.pop()

    assert queued["market_id"] == "1.123"
    assert queued["selection_id"] == 11

    ui_state = {
        "current_market_id": queued["market_id"],
        "current_market_name": queued["market_name"],
        "current_event_name": queued["event_name"],
        "selected_runner_name": queued["selection"],
    }

    assert ui_state["current_market_id"] == "1.123"
    assert ui_state["selected_runner_name"] == "Juve"

    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    payload = {
        "market_id": ui_state["current_market_id"],
        "selection_id": queued["selection_id"],
        "bet_type": queued["side"],
        "price": float(queued["price"]),
        "stake": 10.0,
        "event_name": ui_state["current_event_name"],
        "market_name": ui_state["current_market_name"],
        "runner_name": ui_state["selected_runner_name"],
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert len(db.pending_sagas) == 1
    assert len(db.reconciled) == 1
    assert db.failed == []
    assert len(db.saved_bets) == 1

    success = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1

    evt = success[0][1]
    assert evt["market_id"] == "1.123"
    assert evt["selection_id"] == 11
    assert evt["runner_name"] == "Juve"
    assert evt["status"] == "MATCHED"