import importlib
import sys
import types


def _install_ui_stubs():
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


_install_ui_stubs()

ui_mod = importlib.import_module("app_modules.ui_module")
UIModule = ui_mod.UIModule


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


def _make_ui_module_like():
    ui = UIModule.__new__(UIModule)
    ui.market_type_var = DummyVar()
    ui.available_markets = []
    ui.dutch_modal_btn = DummyButton()
    ui.runners_tree = DummyTree()
    ui.current_market = None
    ui._tree_clear = lambda tree: tree.delete()
    return ui


def test_market_type_selection_sets_current_market_and_enables_button():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {"marketName": "Match Odds", "marketId": "1.123", "runners": []},
        {"marketName": "Over/Under", "marketId": "1.456", "runners": []},
    ]
    ui.market_type_var.set("Match Odds")

    loaded = {"called": 0}

    def fake_load():
        loaded["called"] += 1

    ui._load_runners_for_current_market = fake_load

    UIModule._on_market_type_selected(ui)

    assert ui.current_market["marketId"] == "1.123"
    assert ui.dutch_modal_btn.config["state"] == "normal"
    assert loaded["called"] == 1


def test_market_type_selection_with_unknown_value_keeps_state_unchanged():
    ui = _make_ui_module_like()
    ui.available_markets = [{"marketName": "Match Odds", "marketId": "1.123", "runners": []}]
    ui.market_type_var.set("Unknown Market")

    UIModule._on_market_type_selected(ui)

    assert ui.current_market is None
    assert ui.runners_tree.rows == []


def test_load_runners_for_current_market_populates_tree_rows():
    ui = _make_ui_module_like()
    ui.current_market = {
        "marketId": "1.999",
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

    UIModule._load_runners_for_current_market(ui)

    assert len(ui.runners_tree.rows) == 2
    assert ui.runners_tree.rows[0]["iid"] == "11"
    assert ui.runners_tree.rows[0]["values"][1] == "Juve"
    assert ui.runners_tree.rows[1]["iid"] == "22"
    assert ui.runners_tree.rows[1]["values"][1] == "Milan"


def test_load_runners_for_current_market_handles_missing_market_safely():
    ui = _make_ui_module_like()
    ui.current_market = None

    UIModule._load_runners_for_current_market(ui)

    assert ui.runners_tree.rows == []