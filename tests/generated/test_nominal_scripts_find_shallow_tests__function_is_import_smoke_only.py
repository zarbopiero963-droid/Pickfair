import importlib


def test_nominal_function_is_import_smoke_only_exists():
    module = importlib.import_module("scripts.find_shallow_tests")
    assert hasattr(module, "function_is_import_smoke_only")
