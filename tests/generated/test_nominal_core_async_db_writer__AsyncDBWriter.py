import importlib


def test_nominal_AsyncDBWriter_exists():
    module = importlib.import_module("core.async_db_writer")
    assert hasattr(module, "AsyncDBWriter")
