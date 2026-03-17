import importlib


def test_nominal_FastWoMState_exists():
    module = importlib.import_module("core.fast_analytics")
    assert hasattr(module, "FastWoMState")
