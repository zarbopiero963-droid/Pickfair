import importlib


def test_nominal_check_imports_exists():
    module = importlib.import_module("scripts.check_architecture_rules")
    assert hasattr(module, "check_imports")
