import importlib


def test_nominal_main_exists():
    module = importlib.import_module("scripts.list_top_shallow_tests")
    assert hasattr(module, "main")
