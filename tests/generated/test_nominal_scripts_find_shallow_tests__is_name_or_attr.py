import importlib


def test_nominal_is_name_or_attr_exists():
    module = importlib.import_module("scripts.find_shallow_tests")
    assert hasattr(module, "is_name_or_attr")
