import importlib


def test_nominal_dutching_controller_semantic_probe_case_exists():
    module = importlib.import_module("guardrails.guard_probes")
    assert hasattr(module, "dutching_controller_semantic_probe_case")
