import importlib


def test_nominal_cached_dutching_stakes_exists():
    module = importlib.import_module("dutching_cache")
    assert hasattr(module, "cached_dutching_stakes")
