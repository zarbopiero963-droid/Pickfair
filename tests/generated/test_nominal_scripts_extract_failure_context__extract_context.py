import importlib


def test_nominal_extract_context_exists():
    module = importlib.import_module("scripts.extract_failure_context")
    assert hasattr(module, "extract_context")
