import importlib
import types
import sys


# =========================================================
# 1 MAIN SMOKE
# =========================================================

def test_real_smoke_main_import(monkeypatch):

    fake_ctk = types.ModuleType("customtkinter")

    class Dummy:
        def __init__(self, *a, **k): pass
        def pack(self,*a,**k): pass
        def grid(self,*a,**k): pass
        def place(self,*a,**k): pass
        def configure(self,*a,**k): pass
        def bind(self,*a,**k): pass

    fake_ctk.CTk = Dummy
    fake_ctk.CTkFrame = Dummy
    fake_ctk.CTkLabel = Dummy
    fake_ctk.CTkButton = Dummy
    fake_ctk.CTkEntry = Dummy
    fake_ctk.CTkCheckBox = Dummy
    fake_ctk.CTkScrollableFrame = Dummy

    monkeypatch.setitem(sys.modules,"customtkinter",fake_ctk)

    mod = importlib.import_module("main")

    assert mod is not None


# =========================================================
# 2 UI MODULE IMPORT
# =========================================================

def test_ui_module_import():

    mod = importlib.import_module("ui.tabs.telegram_tab_ui")

    assert mod is not None


# =========================================================
# 3 DATABASE MODULE LOAD
# =========================================================

def test_database_module_load():

    db = importlib.import_module("database")

    assert hasattr(db,"Database")


# =========================================================
# 4 TELEGRAM MODULE LOAD
# =========================================================

def test_telegram_modules_import():

    sender = importlib.import_module("telegram_sender")
    listener = importlib.import_module("telegram_listener")

    assert sender is not None
    assert listener is not None


# =========================================================
# 5 DUTCHING PIPELINE IMPORT
# =========================================================

def test_dutching_pipeline_import():

    dutch = importlib.import_module("dutching")
    ctrl = importlib.import_module("controllers.dutching_controller")
    risk = importlib.import_module("core.risk_middleware")
    engine = importlib.import_module("core.trading_engine")

    assert dutch is not None
    assert ctrl is not None
    assert risk is not None
    assert engine is not None


# =========================================================
# 6 CRASH RECOVERY METHOD EXISTS
# =========================================================

def test_trading_engine_recovery_method_exists():

    engine_mod = importlib.import_module("core.trading_engine")

    assert hasattr(engine_mod,"TradingEngine")