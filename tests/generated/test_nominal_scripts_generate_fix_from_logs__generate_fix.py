import importlib


def test_nominal_generate_fix_exists():
    module = importlib.import_module("scripts.generate_fix_from_logs")
    assert hasattr(module, "generate_fix")
