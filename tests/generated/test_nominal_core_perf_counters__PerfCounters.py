import importlib


def test_nominal_PerfCounters_exists():
    module = importlib.import_module("core.perf_counters")
    assert hasattr(module, "PerfCounters")
