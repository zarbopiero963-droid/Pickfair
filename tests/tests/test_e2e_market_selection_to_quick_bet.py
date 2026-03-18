import importlib
import sys
import types


def _install_ui_and_external_stubs():
    if "customtkinter" not in sys.modules:
        ctk = types.ModuleType("customtkinter")
        ctk.CTkFrame = object
        ctk.CTkLabel = object
        ctk.CTkOptionMenu = object
        ctk.CTkCheckBox = object
        ctk.CTkButton = object
        sys.modules["customtkinter"] = ctk

    if "betfairlightweight" not in sys.modules:
        bflw = types.ModuleType("betfairlightweight")
        bflw.APIClient = object
        bflw.exceptions = types.SimpleNamespace(
            LoginError=Exception,
            CertsError=Exception,
            APIError=Exception,
        )
        bflw.filters = types.SimpleNamespace(
            price_projection=lambda **kwargs: kwargs,
            market_filter=lambda **kwargs: kwargs,
            time_range=lambda **kwargs: kwargs,
        )
        sys.modules["betfairlightweight"] = bflw

    if "betfairlightweight.streaming" not in sys.modules:
        streaming = types.ModuleType("betfairlightweight.streaming")
        streaming.StreamListener = object
        sys.modules["betfairlightweight.streaming"] = streaming


_install_ui_and_external_stubs()

ui_mod = importlib.import_module("app_modules.ui_module")
engine_mod = importlib.import_module("core.trading_engine")

UIModule = ui_mod.UIModule
TradingEngine = engine_mod.TradingEngine


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyButton:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class DummyTree:
    def __init__(self):
        self.rows = []

    def insert(self, parent, index, iid=None, values=(), tags=()):
        self.rows.append(
            {
                "parent": parent,
                "index": index,
                "iid": iid,
                "values": values,
                "tags": tags,
            }
        )

    def delete(self, *args, **kwargs):
        self.rows.clear()

    def get_children(self):
        return list(range(len(self.rows)))


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


def _make_ui_module_like():
    ui = UIModule.__new__(UIModule)
    ui.market_type_var = DummyVar()
    ui.available_markets = []
    ui.dutch_modal_btn = DummyButton()
    ui.runners_tree = DummyTree()
    ui.current_market = None
    ui._tree_clear = lambda tree: tree.delete()
    return ui


def test_e2e_market_selection_to_quick_bet_flow():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {
            "marketName": "Match Odds",
            "marketId": "1.123",
            "eventName": "Juve - Milan",
            "marketType": "MATCH_ODDS",
            "runners": [
                {
                    "selectionId": 11,
                    "runnerName": "Juve",
                    "backPrice": 2.1,
                    "backSize": 100,
                    "layPrice": 2.12,
                    "laySize": 110,
                },
                {
                    "selectionId": 22,
                    "runnerName": "Milan",
                    "backPrice": 3.4,
                    "backSize": 90,
                    "layPrice": 3.5,
                    "laySize": 95,
                },
            ],
        }
    ]
    ui.market_type_var.set("Match Odds")

    UIModule._on_market_type_selected(ui)

    assert ui.current_market["marketId"] == "1.123"
    assert ui.dutch_modal_btn.config["state"] == "normal"
    assert len(ui.runners_tree.rows) == 2
    assert ui.runners_tree.rows[0]["iid"] == "11"

    selected_runner = ui.current_market["runners"][0]

    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    payload = {
        "market_id": ui.current_market["marketId"],
        "selection_id": selected_runner["selectionId"],
        "bet_type": "BACK",
        "price": selected_runner["backPrice"],
        "stake": 10.0,
        "event_name": ui.current_market["eventName"],
        "market_name": ui.current_market["marketName"],
        "runner_name": selected_runner["runnerName"],
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert len(client.place_bet_calls) == 1
    assert len(db.pending_sagas) == 1
    assert len(db.reconciled) == 1
    assert db.failed == []
    assert len(db.saved_bets) == 1

    evt = [x for x in bus.events if x[0] == "QUICK_BET_SUCCESS"][0][1]
    assert evt["market_id"] == "1.123"
    assert evt["selection_id"] == 11
    assert evt["runner_name"] == "Juve"
    assert evt["status"] == "MATCHED"