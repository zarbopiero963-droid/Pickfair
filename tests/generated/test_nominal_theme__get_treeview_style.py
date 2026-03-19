import importlib


def test_nominal_get_treeview_style_exists():
    module = importlib.import_module("theme")
    assert hasattr(module, "get_treeview_style")
