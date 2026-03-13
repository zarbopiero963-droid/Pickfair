from order_manager import OrderManager


def test_order_manager_reports_unsupported_cancel_and_replace_cleanly():
    manager = OrderManager()

    cancel_result = manager.cancel_order("1.123", "BET123")
    replace_result = manager.replace_order("1.123", "BET123", 2.5)

    assert cancel_result is False
    assert replace_result is False


def test_order_manager_local_cache_lifecycle():
    manager = OrderManager()

    manager.remember("bet_1", {"status": "PENDING", "market_id": "1.123"})
    cached = manager.get_cached("bet_1")

    assert cached["status"] == "PENDING"
    assert cached["market_id"] == "1.123"

    manager.forget("bet_1")

    assert manager.get_cached("bet_1") is None