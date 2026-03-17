import importlib


def test_nominal_dutching_controller_runtime_smoke_exists():
    module = importlib.import_module("guardrails.guard_probes")
    assert hasattr(module, "dutching_controller_runtime_smoke")
