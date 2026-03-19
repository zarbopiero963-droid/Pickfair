import importlib


def test_nominal_run_tests_exists():
    module = importlib.import_module("scripts.run_targeted_tests")
    assert hasattr(module, "run_tests")
