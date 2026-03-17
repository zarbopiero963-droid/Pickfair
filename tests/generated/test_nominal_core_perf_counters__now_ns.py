import importlib


def test_nominal_now_ns_exists():
    module = importlib.import_module("core.perf_counters")
    assert hasattr(module, "now_ns")
