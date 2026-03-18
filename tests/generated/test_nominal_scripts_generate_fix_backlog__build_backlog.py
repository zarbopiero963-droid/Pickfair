import importlib


def test_nominal_build_backlog_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "build_backlog")
