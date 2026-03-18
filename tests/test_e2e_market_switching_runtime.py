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


def test_e2e_market_switching_runtime_updates_current_market_and_tree():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {
            "marketName": "Match Odds",
            "marketId": "1.100",
            "runners": [
                {
                    "selectionId": 11,
                    "runnerName": "Home",
                    "backPrice": 2.0,
                    "backSize": 100,
                    "layPrice": 2.02,
                    "laySize": 110,
                },
                {
                    "selectionId": 22,
                    "runnerName": "Away",
                    "backPrice": 3.5,
                    "backSize": 80,
                    "layPrice": 3.6,
                    "laySize": 90,
                },
            ],
        },
        {
            "marketName": "Over/Under 2.5",
            "marketId": "1.200",
            "runners": [
                {
                    "selectionId": 33,
                    "runnerName": "Over 2.5",
                    "backPrice": 2.1,
                    "backSize": 70,
                    "layPrice": 2.12,
                    "laySize": 75,
                },
                {
                    "selectionId": 44,
                    "runnerName": "Under 2.5",
                    "backPrice": 1.8,
                    "backSize": 120,
                    "layPrice": 1.82,
                    "laySize": 130,
                },
            ],
        },
    ]

    ui.market_type_var.set("Match Odds")
    UIModule._on_market_type_selected(ui)

    assert ui.current_market["marketId"] == "1.100"
    assert len(ui.runners_tree.rows) == 2
    assert ui.runners_tree.rows[0]["iid"] == "11"
    assert ui.runners_tree.rows[0]["values"][1] == "Home"

    ui.market_type_var.set("Over/Under 2.5")
    UIModule._on_market_type_selected(ui)

    assert ui.current_market["marketId"] == "1.200"
    assert len(ui.runners_tree.rows) == 2
    assert ui.runners_tree.rows[0]["iid"] == "33"
    assert ui.runners_tree.rows[0]["values"][1] == "Over 2.5"


def test_e2e_market_switching_runtime_clears_previous_runner_rows():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {
            "marketName": "Match Odds",
            "marketId": "1.300",
            "runners": [
                {
                    "selectionId": 10,
                    "runnerName": "Alpha",
                    "backPrice": 2.2,
                    "backSize": 100,
                    "layPrice": 2.24,
                    "laySize": 100,
                }
            ],
        },
        {
            "marketName": "Correct Score",
            "marketId": "1.400",
            "runners": [
                {
                    "selectionId": 20,
                    "runnerName": "1-0",
                    "backPrice": 7.0,
                    "backSize": 20,
                    "layPrice": 7.2,
                    "laySize": 25,
                },
                {
                    "selectionId": 21,
                    "runnerName": "2-0",
                    "backPrice": 9.0,
                    "backSize": 15,
                    "layPrice": 9.4,
                    "laySize": 18,
                },
            ],
        },
    ]

    ui.market_type_var.set("Match Odds")
    UIModule._on_market_type_selected(ui)
    assert len(ui.runners_tree.rows) == 1

    ui.market_type_var.set("Correct Score")
    UIModule._on_market_type_selected(ui)

    assert len(ui.runners_tree.rows) == 2
    values = [row["values"][1] for row in ui.runners_tree.rows]
    assert values == ["1-0", "2-0"]


def test_e2e_market_switching_runtime_unknown_selection_is_safe():
    ui = _make_ui_module_like()
    ui.available_markets = [
        {"marketName": "Match Odds", "marketId": "1.500", "runners": []}
    ]
    ui.market_type_var.set("Not Existing")

    UIModule._on_market_type_selected(ui)

    assert ui.current_market is None
    assert ui.runners_tree.rows == []