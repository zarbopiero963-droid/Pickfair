import importlib


def test_nominal_estimate_complexity_exists():
    module = importlib.import_module("scripts.repo_api_report_v4")
    assert hasattr(module, "estimate_complexity")
