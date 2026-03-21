import importlib


def test_nominal_BettingModule_exists():
    module = importlib.import_module("app_modules.betting_module")
    assert hasattr(module, "BettingModule")
