import importlib


def test_nominal_main_exists():
    module = importlib.import_module("scripts.prioritize_test_cleanup")
    assert hasattr(module, "main")
