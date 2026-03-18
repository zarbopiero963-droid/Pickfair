import importlib


def test_nominal_validate_payload_exists():
    module = importlib.import_module("scripts.check_contract_snapshots")
    assert hasattr(module, "validate_payload")
