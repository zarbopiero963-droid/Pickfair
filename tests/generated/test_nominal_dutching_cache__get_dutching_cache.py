import importlib


def test_nominal_get_dutching_cache_exists():
    module = importlib.import_module("dutching_cache")
    assert hasattr(module, "get_dutching_cache")
