import importlib


def test_nominal_build_symbol_locations_exists():
    module = importlib.import_module("scripts.repo_api_report_v4")
    assert hasattr(module, "build_symbol_locations")
