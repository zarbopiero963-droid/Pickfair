import importlib


def test_nominal_configure_customtkinter_exists():
    module = importlib.import_module("theme")
    assert hasattr(module, "configure_customtkinter")
