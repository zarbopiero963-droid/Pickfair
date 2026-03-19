import importlib

MODULES = [
    "database",
    "pnl_engine",
    "telegram_listener",
    "telegram_sender",
    "telegram_controller",
    "core.trading_engine",
    "core.safety_layer",
    "ai.ai_guardrail",
]


def test_modules_import_cleanly():
    for module_name in MODULES:
        mod = importlib.import_module(module_name)
        assert mod is not None


def test_trading_engine_class_exists():
    mod = importlib.import_module("core.trading_engine")
    assert hasattr(mod, "TradingEngine")


def test_database_class_exists():
    mod = importlib.import_module("database")
    assert hasattr(mod, "Database")


def test_guardrail_classes_exist():
    mod = importlib.import_module("ai.ai_guardrail")

    assert hasattr(mod, "AIGuardrail")
    assert hasattr(mod, "GuardrailConfig")


def test_safety_layer_exists():
    mod = importlib.import_module("core.safety_layer")

    assert hasattr(mod, "SafetyLayer")