import importlib


def test_nominal_analyze_repo_exists():
    module = importlib.import_module("scripts.repo_api_report_v4")
    assert hasattr(module, "analyze_repo")
