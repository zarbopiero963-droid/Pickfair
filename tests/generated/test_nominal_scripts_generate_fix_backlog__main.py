import importlib


def test_nominal_main_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "main")
