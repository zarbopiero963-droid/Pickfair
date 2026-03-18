import importlib


def test_nominal_classify_assert_exists():
    module = importlib.import_module("scripts.find_shallow_tests")
    assert hasattr(module, "classify_assert")
