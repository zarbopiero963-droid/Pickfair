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
                self.children = []

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

            def withdraw(self):
                return None

            def deiconify(self):
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
            self.args = args
            self.kwargs = kwargs

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

        def bind(self, *args, **kwargs):
            return None

    tk.StringVar = DummyVar
    tk.BooleanVar = DummyVar
    tk.IntVar = DummyVar
    tk.DoubleVar = DummyVar
    tk.Canvas = DummyCanvas
    tk.BOTH = "both"
    tk.LEFT = "left"
    tk.RIGHT = "right"
    tk.VERTICAL = "vertical"
    tk.W = "w"
    tk.X = "x"
    tk.Y = "y"
    tk.END = "end"

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
toolbar_mod = importlib.import_module("ui.toolbar")
mini_mod = importlib.import_module("ui.mini_ladder")
telegram_tab_mod = importlib.import_module("ui.tabs.telegram_tab_ui")
ui_module_mod = importlib.import_module("app_modules.ui_module")


def test_gui_manual_smoke_imports_core_gui_modules():
    assert hasattr(main_mod, "PickfairApp")
    assert hasattr(toolbar_mod, "Toolbar")
    assert hasattr(mini_mod, "MiniLadder")
    assert hasattr(telegram_tab_mod, "TelegramTabUI")
    assert hasattr(ui_module_mod, "UIModule")


def test_gui_manual_smoke_pickfair_metadata_exists():
    assert hasattr(main_mod, "APP_NAME")
    assert hasattr(main_mod, "APP_VERSION")
    assert isinstance(main_mod.APP_NAME, str)
    assert isinstance(main_mod.APP_VERSION, str)
    assert main_mod.APP_NAME.strip()
    assert main_mod.APP_VERSION.strip()


def test_gui_manual_smoke_toolbar_runtime_handlers_exist():
    Toolbar = toolbar_mod.Toolbar

    assert hasattr(Toolbar, "_cmd_toggle_sim")
    assert hasattr(Toolbar, "_cmd_panic_cashout")
    assert hasattr(Toolbar, "_on_safe_mode_update")
    assert hasattr(Toolbar, "_wire_events")


def test_gui_manual_smoke_mini_ladder_runtime_methods_exist():
    MiniLadder = mini_mod.MiniLadder

    assert hasattr(MiniLadder, "_extract_back_price")
    assert hasattr(MiniLadder, "_extract_lay_price")
    assert hasattr(MiniLadder, "_get_current_stake")
    assert hasattr(MiniLadder, "update_prices")


def test_gui_manual_smoke_telegram_tab_runtime_methods_exist():
    TelegramTabUI = telegram_tab_mod.TelegramTabUI

    assert hasattr(TelegramTabUI, "_safe_settings")
    assert hasattr(TelegramTabUI, "_build")


def test_gui_manual_smoke_ui_module_runtime_methods_exist():
    UIModule = ui_module_mod.UIModule

    assert hasattr(UIModule, "_on_market_type_selected")
    assert hasattr(UIModule, "_load_runners_for_current_market")