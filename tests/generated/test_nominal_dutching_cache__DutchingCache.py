import importlib


def test_nominal_DutchingCache_exists():
    module = importlib.import_module("dutching_cache")
    assert hasattr(module, "DutchingCache")
