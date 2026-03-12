import pytest

from order_manager import OrderManager


def test_order_recovery_logic():
    om = OrderManager()

    pending = [{"betId": "1"}]

    assert len(pending) == 1