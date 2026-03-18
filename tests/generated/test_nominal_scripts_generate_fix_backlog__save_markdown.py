import importlib


def test_nominal_save_markdown_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "save_markdown")
