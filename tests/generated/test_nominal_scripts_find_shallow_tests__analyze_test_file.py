import importlib


def test_nominal_analyze_test_file_exists():
    module = importlib.import_module("scripts.find_shallow_tests")
    assert hasattr(module, "analyze_test_file")
