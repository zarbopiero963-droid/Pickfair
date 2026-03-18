import importlib


def test_nominal_run_mutation_probes_exists():
    module = importlib.import_module("tools.ai_reasoning_guard")
    assert hasattr(module, "run_mutation_probes")
