import importlib


def test_nominal_AIPatternEngine_exists():
    module = importlib.import_module("ai.ai_pattern_engine")
    assert hasattr(module, "AIPatternEngine")
