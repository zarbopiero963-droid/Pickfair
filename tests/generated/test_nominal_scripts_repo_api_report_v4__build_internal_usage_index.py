import importlib


def test_nominal_build_internal_usage_index_exists():
    module = importlib.import_module("scripts.repo_api_report_v4")
    assert hasattr(module, "build_internal_usage_index")
