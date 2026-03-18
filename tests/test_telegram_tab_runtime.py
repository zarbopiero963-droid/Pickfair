import importlib
import sys
import types


def _install_ui_stubs():
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
        ctk.CTkEntry = DummyWidget
        ctk.CTkButton = DummyWidget
        ctk.CTkCheckBox = DummyWidget
        sys.modules["customtkinter"] = ctk

    if "tkinter" in sys.modules:
        tk = sys.modules["tkinter"]
    else:
        tk = types.ModuleType("tkinter")
        sys.modules["tkinter"] = tk

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


_install_ui_stubs()

tab_mod = importlib.import_module("ui.tabs.telegram_tab_ui")
TelegramTabUI = tab_mod.TelegramTabUI


class DummyDB:
    def __init__(self, settings=None, should_fail=False):
        self._settings = settings or {}
        self._should_fail = should_fail

    def get_telegram_settings(self):
        if self._should_fail:
            raise RuntimeError("db error")
        return dict(self._settings)


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
    def __init__(self, settings=None, should_fail=False):
        self.db = DummyDB(settings=settings, should_fail=should_fail)
        self.telegram_controller = DummyTelegramController()
        self.telegram_status = "STOPPED"

    def _start_telegram_listener(self):
        return None


def test_safe_settings_returns_db_values():
    ui = TelegramTabUI.__new__(TelegramTabUI)
    ui.app = DummyApp(settings={"api_id": "123", "api_hash": "hash", "auto_bet": True})

    settings = TelegramTabUI._safe_settings(ui)

    assert settings["api_id"] == "123"
    assert settings["api_hash"] == "hash"
    assert settings["auto_bet"] is True


def test_safe_settings_returns_empty_dict_on_db_error():
    ui = TelegramTabUI.__new__(TelegramTabUI)
    ui.app = DummyApp(should_fail=True)

    settings = TelegramTabUI._safe_settings(ui)

    assert settings == {}


def test_build_populates_app_variables_from_settings():
    app = DummyApp(
        settings={
            "api_id": "999",
            "api_hash": "abc123",
            "phone_number": "+391234",
            "auto_stake": 3.5,
            "auto_bet": True,
            "require_confirmation": False,
        }
    )

    ui = TelegramTabUI(parent_frame=object(), app=app)

    assert app.tg_api_id_var.get() == "999"
    assert app.tg_api_hash_var.get() == "abc123"
    assert app.tg_phone_var.get() == "+391234"
    assert app.tg_auto_stake_var.get() == "3.5"
    assert app.tg_auto_bet_var.get() is True
    assert app.tg_confirm_var.get() is False
    assert hasattr(app, "tg_status_label")