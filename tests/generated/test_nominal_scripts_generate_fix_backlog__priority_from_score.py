import importlib


def test_nominal_priority_from_score_exists():
    module = importlib.import_module("scripts.generate_fix_backlog")
    assert hasattr(module, "priority_from_score")
