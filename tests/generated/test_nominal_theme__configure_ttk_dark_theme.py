import importlib


def test_nominal_configure_ttk_dark_theme_exists():
    module = importlib.import_module("theme")
    assert hasattr(module, "configure_ttk_dark_theme")
