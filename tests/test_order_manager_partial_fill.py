import pytest

from order_manager import OrderManager


def test_partial_fill_handling():
    om = OrderManager()

    order = {"size": 10, "matched": 5}

    remaining = order["size"] - order["matched"]

    assert remaining == 5