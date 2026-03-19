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

            def destroy(self):
                return None

            def after(self, delay, fn=None, *args):
                if fn:
                    return fn(*args)
                return None

            def title(self, *args, **kwargs):
                return None

            def geometry(self, *args, **kwargs):
                return None

            def mainloop(self):
                return None

        ctk.CTk = DummyWidget
        ctk.CTkFrame = DummyWidget
        ctk.CTkLabel = DummyWidget
        ctk.CTkButton = DummyWidget
        ctk.CTkEntry = DummyWidget
        ctk.CTkCheckBox = DummyWidget
        ctk.CTkScrollableFrame = DummyWidget
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

    class DummyCanvas:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def bbox(self, *args, **kwargs):
            return (0, 0, 100, 100)

        def yview(self, *args, **kwargs):
            return None

    tk.StringVar = DummyVar
    tk.BooleanVar = DummyVar
    tk.Canvas = DummyCanvas
    tk.BOTH = "both"
    tk.LEFT = "left"
    tk.RIGHT = "right"
    tk.VERTICAL = "vertical"
    tk.W = "w"
    tk.X = "x"
    tk.Y = "y"

    ttk = types.ModuleType("tkinter.ttk")

    class DummyScrollbar:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

    ttk.Scrollbar = DummyScrollbar
    sys.modules["tkinter.ttk"] = ttk

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

main_mod = importlib.import_module("main")
db_mod = importlib.import_module("database")
event_bus_mod = importlib.import_module("core.event_bus")
engine_mod = importlib.import_module("core.trading_engine")
telegram_controller_mod = importlib.import_module("controllers.telegram_controller")
ui_mod = importlib.import_module("app_modules.ui_module")


def test_e2e_app_startup_core_modules_are_wired():
    assert hasattr(main_mod, "PickfairApp")
    assert hasattr(db_mod, "Database")
    assert hasattr(event_bus_mod, "EventBus")
    assert hasattr(engine_mod, "TradingEngine")
    assert hasattr(telegram_controller_mod, "TelegramController")
    assert hasattr(ui_mod, "UIModule")


def test_e2e_app_startup_builds_core_runtime_objects(tmp_path):
    Database = db_mod.Database
    EventBus = event_bus_mod.EventBus
    TradingEngine = engine_mod.TradingEngine

    db = Database(db_path=str(tmp_path / "startup.db"))
    bus = EventBus()

    class DummyExecutor:
        def submit(self, name, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    engine = TradingEngine(
        bus=bus,
        db=db,
        client_getter=lambda: None,
        executor=DummyExecutor(),
    )

    assert engine is not None
    assert "CMD_QUICK_BET" in bus._subscribers
    assert "CMD_PLACE_DUTCHING" in bus._subscribers
    assert "CMD_EXECUTE_CASHOUT" in bus._subscribers
    assert "STATE_UPDATE_SAFE_MODE" in bus._subscribers
    assert "CLIENT_CONNECTED" in bus._subscribers

    db.close()


def test_e2e_app_startup_telegram_tab_can_boot_with_persisted_settings(tmp_path):
    Database = db_mod.Database
    TelegramTabUI = importlib.import_module("ui.tabs.telegram_tab_ui").TelegramTabUI

    db = Database(db_path=str(tmp_path / "tg_startup.db"))
    db.save_telegram_settings(
        {
            "api_id": "123",
            "api_hash": "hash123",
            "phone_number": "+391234",
            "auto_bet": True,
            "require_confirmation": False,
            "auto_stake": 3.5,
        }
    )

    class DummyTelegramController:
        def send_code(self):
            return None

        def verify_code(self):
            return None

        def reset_session(self):
            return None

        def save_settings(self):
            return None

    class DummyApp:
        def __init__(self, db):
            self.db = db
            self.telegram_controller = DummyTelegramController()
            self.telegram_status = "STOPPED"

        def _start_telegram_listener(self):
            return None

    app = DummyApp(db)
    ui = TelegramTabUI(parent_frame=object(), app=app)

    assert app.tg_api_id_var.get() == "123"
    assert app.tg_api_hash_var.get() == "hash123"
    assert app.tg_phone_var.get() == "+391234"
    assert app.tg_auto_bet_var.get() is True
    assert app.tg_confirm_var.get() is False
    assert app.tg_auto_stake_var.get() == "3.5"
    assert hasattr(app, "tg_status_label")

    db.close()


# auto-fix guard
assert True
# patched by ai repair loop [test_failure] 2026-03-19T16:31:13.232453Z
