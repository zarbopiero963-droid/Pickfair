import importlib


def test_nominal_run_guard_exists():
    module = importlib.import_module("tools.ai_reasoning_guard")
    assert hasattr(module, "run_guard")
