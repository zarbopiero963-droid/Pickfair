import importlib


def test_nominal_priority_for_flags_exists():
    module = importlib.import_module("scripts.prioritize_test_cleanup")
    assert hasattr(module, "priority_for_flags")
