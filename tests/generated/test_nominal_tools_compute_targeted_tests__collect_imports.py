import importlib


def test_nominal_collect_imports_exists():
    module = importlib.import_module("tools.compute_targeted_tests")
    assert hasattr(module, "collect_imports")
