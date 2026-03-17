import importlib


def test_nominal_build_exists():
    module = importlib.import_module("build")
    assert hasattr(module, "build")
