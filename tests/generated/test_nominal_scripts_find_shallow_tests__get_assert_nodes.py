import importlib


def test_nominal_get_assert_nodes_exists():
    module = importlib.import_module("scripts.find_shallow_tests")
    assert hasattr(module, "get_assert_nodes")
