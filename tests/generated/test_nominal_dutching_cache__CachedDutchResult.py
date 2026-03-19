import importlib


def test_nominal_CachedDutchResult_exists():
    module = importlib.import_module("dutching_cache")
    assert hasattr(module, "CachedDutchResult")
