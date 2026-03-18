import importlib
import sys
import types


def _install_ui_stubs():
    if "customtkinter" not in sys.modules:
        ctk = types.ModuleType("customtkinter")
        ctk.CTkFrame = object
        ctk.CTkLabel = object
        ctk.CTkButton = object
        sys.modules["customtkinter"] = ctk


_install_ui_stubs()

mini_mod = importlib.import_module("ui.mini_ladder")
MiniLadder = mini_mod.MiniLadder


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


class DummyApp:
    def __init__(self):
        self.stake_var = DummyVar("5.0")
        self.simulation_mode = False


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


def test_e2e_live_price_update_to_ui_flow_updates_ladder_state_and_buttons():
    ladder = _make_ladder_like()

    MiniLadder.update_prices(ladder, new_back=2.5, new_lay=2.6)

    assert ladder.selection_data["backPrice"] == 2.5
    assert ladder.selection_data["layPrice"] == 2.6
    assert ladder.btn_back.config["text"] == "2.50"
    assert ladder.btn_lay.config["text"] == "2.60"


def test_e2e_live_price_update_to_ui_flow_multiple_updates_keep_latest_values():
    ladder = _make_ladder_like()

    MiniLadder.update_prices(ladder, new_back=2.2, new_lay=2.3)
    MiniLadder.update_prices(ladder, new_back=2.4, new_lay=2.5)
    MiniLadder.update_prices(ladder, new_back=2.8, new_lay=2.9)

    assert ladder.selection_data["backPrice"] == 2.8
    assert ladder.selection_data["layPrice"] == 2.9
    assert ladder.btn_back.config["text"] == "2.80"
    assert ladder.btn_lay.config["text"] == "2.90"


def test_e2e_live_price_update_to_ui_flow_preserves_runner_identity():
    ladder = _make_ladder_like()

    original_selection_id = ladder.selection_data["selectionId"]
    original_runner_name = ladder.selection_data["runnerName"]

    MiniLadder.update_prices(ladder, new_back=1.98, new_lay=2.0)

    assert ladder.selection_data["selectionId"] == original_selection_id
    assert ladder.selection_data["runnerName"] == original_runner_name
    assert ladder.btn_back.config["text"] == "1.98"
    assert ladder.btn_lay.config["text"] == "2.00"