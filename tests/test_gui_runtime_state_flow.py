import importlib
import sys
import types


def _install_ui_and_external_stubs():
    if "customtkinter" not in sys.modules:
        ctk = types.ModuleType("customtkinter")

        class DummyWidget:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.config = dict(kwargs)

            def pack(self, *args, **kwargs):
                return None

            def grid(self, *args, **kwargs):
                return None

            def place(self, *args, **kwargs):
                return None

            def pack_propagate(self, *args, **kwargs):
                return None

            def bind(self, *args, **kwargs):
                return None

            def configure(self, **kwargs):
                self.config.update(kwargs)

            def create_window(self, *args, **kwargs):
                return None

            def bbox(self, *args, **kwargs):
                return (0, 0, 100, 100)

            def yview(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return None

        ctk.CTkFrame = DummyWidget
        ctk.CTkLabel = DummyWidget
        ctk.CTkButton = DummyWidget
        ctk.CTkSwitch = DummyWidget
        ctk.CTkOptionMenu = DummyWidget
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

toolbar_mod = importlib.import_module("ui.toolbar")
mini_mod = importlib.import_module("ui.mini_ladder")
ui_mod = importlib.import_module("app_modules.ui_module")

Toolbar = toolbar_mod.Toolbar
MiniLadder = mini_mod.MiniLadder
UIModule = ui_mod.UIModule


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


class DummyUIQ:
    def post(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyIndicator:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class DummyButton:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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


class DummyApp:
    def __init__(self):
        self.uiq = DummyUIQ()
        self.simulation_var = DummyVar(False)
        self.current_market = {"marketId": "1.123"}
        self.market_cashout_positions = {}
        self.toggle_calls = 0
        self.stake_var = DummyVar("5.0")
        self.simulation_mode = False

    def _toggle_simulation(self):
        self.toggle_calls += 1


def _make_toolbar_like():
    tb = Toolbar.__new__(Toolbar)
    tb.app = DummyApp()
    tb.bus = DummyBus()
    tb.status_indicator = DummyIndicator()
    tb.btn_cashout_all = DummyButton()
    return tb


def _make_ladder_like():
    ladder = MiniLadder.__new__(MiniLadder)
    ladder.app = DummyApp()
    ladder.bus = DummyBus()
    ladder.market_data = {
        "marketId": "1.200",
        "marketType": "MATCH_ODDS",
        "eventName": "A - B",
        "marketName": "Match Odds",
    }
    ladder.selection_data = {
        "selectionId": 10,
        "runnerName": "Runner A",
        "backPrice": 2.0,
        "layPrice": 2.1,
    }
    ladder.btn_back = DummyButton()
    ladder.btn_lay = DummyButton()
    return ladder


def _make_ui_module_like():
    ui = UIModule.__new__(UIModule)
    ui.market_type_var = DummyVar()
    ui.available_markets = []
    ui.dutch_modal_btn = DummyButton()
    ui.runners_tree = DummyTree()
    ui.current_market = None
    ui._tree_clear = lambda tree: tree.delete()
    return ui


def test_gui_runtime_state_flow_toolbar_safe_mode_to_operational():
    tb = _make_toolbar_like()

    Toolbar._on_safe_mode_update(tb, {"enabled": True, "reason": "Circuit Breaker"})
    assert "SAFE MODE" in tb.status_indicator.config["text"]

    Toolbar._on_safe_mode_update(tb, False)
    assert tb.status_indicator.config["text"] == "🟢 SISTEMA OPERATIVO"


def test_gui_runtime_state_flow_toolbar_toggle_sim_calls_app():
    tb = _make_toolbar_like()

    Toolbar._cmd_toggle_sim(tb)

    assert tb.app.toggle_calls == 1


def test_gui_runtime_state_flow_mini_ladder_updates_prices_and_buttons():
    ladder = _make_ladder_like()

    MiniLadder.update_prices(ladder, new_back=2.5, new_lay=2.6)

    assert ladder.selection_data["backPrice"] == 2.5
    assert ladder.selection_data["layPrice"] == 2.6
    assert ladder.btn_back.config["text"] == "2.50"
    assert ladder.btn_lay.config["text"] == "2.60"


def test_gui_runtime_state_flow_market_selection_populates_runner_tree():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {
            "marketName": "Match Odds",
            "marketId": "1.123",
            "runners": [
                {
                    "selectionId": 11,
                    "runnerName": "Juve",
                    "backPrice": 2.1,
                    "backSize": 100,
                    "layPrice": 2.12,
                    "laySize": 120,
                },
                {
                    "selectionId": 22,
                    "runnerName": "Milan",
                    "backPrice": 3.4,
                    "backSize": 80,
                    "layPrice": 3.5,
                    "laySize": 90,
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
    assert ui.runners_tree.rows[0]["values"][1] == "Juve"


def test_gui_runtime_state_flow_market_selection_unknown_value_is_safe():
    ui = _make_ui_module_like()
    ui.available_markets = [{"marketName": "Match Odds", "marketId": "1.123", "runners": []}]
    ui.market_type_var.set("Unknown Market")

    UIModule._on_market_type_selected(ui)

    assert ui.current_market is None
    assert ui.runners_tree.rows == []