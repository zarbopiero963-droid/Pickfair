import importlib


def test_nominal_find_targeted_tests_exists():
    module = importlib.import_module("tools.compute_targeted_tests")
    assert hasattr(module, "find_targeted_tests")
