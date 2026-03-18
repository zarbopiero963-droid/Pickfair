import importlib


def test_nominal_load_report_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "load_report")
