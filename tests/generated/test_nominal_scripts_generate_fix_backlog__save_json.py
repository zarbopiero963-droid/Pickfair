import importlib


def test_nominal_save_json_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "save_json")
