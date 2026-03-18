import importlib
import sys
import types

from core.event_bus import EventBus
from core.trading_engine import TradingEngine
from database import Database


def _install_customtkinter_stub(monkeypatch):
    fake_ctk = types.ModuleType("customtkinter")

    class Dummy:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def place(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def pack_propagate(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

    fake_ctk.CTk = Dummy
    fake_ctk.CTkFrame = Dummy
    fake_ctk.CTkLabel = Dummy
    fake_ctk.CTkButton = Dummy
    fake_ctk.CTkEntry = Dummy
    fake_ctk.CTkCheckBox = Dummy
    fake_ctk.CTkScrollableFrame = Dummy
    fake_ctk.CTkSwitch = Dummy

    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)


def _install_telethon_stub(monkeypatch):
    telethon_mod = types.ModuleType("telethon")
    telethon_mod.TelegramClient = object
    telethon_mod.events = object()

    sessions_mod = types.ModuleType("telethon.sessions")

    class DummyStringSession:
        def __init__(self, *args, **kwargs):
            pass

    sessions_mod.StringSession = DummyStringSession

    monkeypatch.setitem(sys.modules, "telethon", telethon_mod)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions_mod)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    pass


def test_real_smoke_main_import(monkeypatch):
    _install_customtkinter_stub(monkeypatch)
    _install_telethon_stub(monkeypatch)

    mod = importlib.import_module("main")

    assert hasattr(mod, "PickfairApp")
    assert hasattr(mod, "APP_NAME")
    assert hasattr(mod, "APP_VERSION")
    assert isinstance(mod.APP_NAME, str)
    assert isinstance(mod.APP_VERSION, str)


def test_ui_module_import_and_contract(monkeypatch):
    _install_customtkinter_stub(monkeypatch)

    mod = importlib.import_module("ui.tabs.telegram_tab_ui")
    assert hasattr(mod, "TelegramTabUI")

    TelegramTabUI = mod.TelegramTabUI

    class DummyDBWithSettings:
        def get_telegram_settings(self):
            return {
                "api_id": "123",
                "api_hash": "hash",
                "phone_number": "+391234",
            }

    class DummyApp:
        db = DummyDBWithSettings()

    ui = TelegramTabUI.__new__(TelegramTabUI)
    ui.app = DummyApp()

    settings = ui._safe_settings()

    assert settings["api_id"] == "123"
    assert settings["api_hash"] == "hash"
    assert settings["phone_number"] == "+391234"


def test_database_module_load_and_real_settings_roundtrip(tmp_path):
    db_path = tmp_path / "pickfair_test.db"
    db = Database(db_path=str(db_path))

    payload = {
        "api_id": "999",
        "api_hash": "abc123",
        "phone_number": "+390000",
        "enabled": True,
        "auto_bet": True,
        "require_confirmation": False,
        "auto_stake": 3.5,
        "master_chat_id": "111",
        "publisher_chat_id": "222",
    }

    db.save_telegram_settings(payload)
    settings = db.get_telegram_settings()

    assert settings["api_id"] == "999"
    assert settings["api_hash"] == "abc123"
    assert settings["phone_number"] == "+390000"
    assert settings["enabled"] is True
    assert settings["auto_bet"] is True
    assert settings["require_confirmation"] is False
    assert settings["auto_stake"] == 3.5
    assert settings["master_chat_id"] == "111"
    assert settings["publisher_chat_id"] == "222"

    db.close()


def test_telegram_modules_import_and_real_parser_contract(monkeypatch):
    _install_telethon_stub(monkeypatch)

    sender = importlib.import_module("telegram_sender")
    listener = importlib.import_module("telegram_listener")

    assert hasattr(sender, "TelegramSender")
    assert hasattr(listener, "TelegramListener")
    assert hasattr(listener, "SignalQueue")
    assert hasattr(listener, "parse_signal_message")

    msg = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11"
    )
    parsed = listener.parse_signal_message(msg)

    assert parsed is not None
    assert parsed["market_id"] == "1.123"
    assert parsed["selection_id"] == 11
    assert parsed["side"] == "BACK"
    assert float(parsed["price"]) == 2.10


def test_dutching_pipeline_import_and_runtime_contract():
    dutch = importlib.import_module("dutching")
    ctrl = importlib.import_module("controllers.dutching_controller")
    engine_mod = importlib.import_module("core.trading_engine")

    assert hasattr(dutch, "calculate_dutching_stakes")
    assert hasattr(ctrl, "DutchingController")
    assert hasattr(engine_mod, "TradingEngine")

    stakes = dutch.calculate_dutching_stakes(
        selections=[
            {"selectionId": 1, "price": 2.0},
            {"selectionId": 2, "price": 4.0},
        ],
        total_stake=12.0,
    )

    assert isinstance(stakes, list)
    assert len(stakes) == 2
    assert sum(float(row["stake"]) for row in stakes) == 12.0


def test_trading_engine_recovery_and_subscription_contracts():
    bus = EventBus()
    engine = TradingEngine(
        bus=bus,
        db=DummyDB(),
        client_getter=lambda: None,
        executor=DummyExecutor(),
    )

    assert hasattr(engine, "_recover_pending_sagas")
    assert "CMD_QUICK_BET" in bus._subscribers
    assert "CMD_PLACE_DUTCHING" in bus._subscribers
    assert "CMD_EXECUTE_CASHOUT" in bus._subscribers
    assert "STATE_UPDATE_SAFE_MODE" in bus._subscribers
    assert "CLIENT_CONNECTED" in bus._subscribers

    engine._toggle_kill_switch({"enabled": True})
    assert engine.is_killed is True

    engine._toggle_kill_switch(False)
    assert engine.is_killed is False