from order_manager import OrderManager


def test_order_manager_can_store_and_replace_partial_fill_state():
    manager = OrderManager()

    manager.remember(
        "BET-1",
        {
            "betId": "BET-1",
            "status": "PARTIALLY_MATCHED",
            "sizeMatched": 4.0,
            "sizeRemaining": 6.0,
        },
    )

    cached = manager.get_cached("BET-1")

    assert cached["status"] == "PARTIALLY_MATCHED"
    assert cached["sizeMatched"] == 4.0
    assert cached["sizeRemaining"] == 6.0

    manager.remember(
        "BET-1",
        {
            "betId": "BET-1",
            "status": "MATCHED",
            "sizeMatched": 10.0,
            "sizeRemaining": 0.0,
        },
    )

    cached_after = manager.get_cached("BET-1")

    assert cached_after["status"] == "MATCHED"
    assert cached_after["sizeMatched"] == 10.0
    assert cached_after["sizeRemaining"] == 0.0


def test_order_manager_multiple_partial_orders_are_isolated():
    manager = OrderManager()

    manager.remember(
        "BET-A",
        {"status": "PARTIALLY_MATCHED", "sizeMatched": 2.0, "sizeRemaining": 3.0},
    )
    manager.remember(
        "BET-B",
        {"status": "PARTIALLY_MATCHED", "sizeMatched": 1.5, "sizeRemaining": 8.5},
    )

    a = manager.get_cached("BET-A")
    b = manager.get_cached("BET-B")

    assert a["sizeMatched"] == 2.0
    assert a["sizeRemaining"] == 3.0
    assert b["sizeMatched"] == 1.5
    assert b["sizeRemaining"] == 8.5


def test_order_manager_forget_partial_order_removes_only_target():
    manager = OrderManager()

    manager.remember("BET-A", {"status": "PARTIALLY_MATCHED"})
    manager.remember("BET-B", {"status": "MATCHED"})

    manager.forget("BET-A")

    assert manager.get_cached("BET-A") is None
    assert manager.get_cached("BET-B") == {"status": "MATCHED"}


def test_order_manager_status_counts_partial_fill_cache_entries():
    manager = OrderManager()

    manager.remember("BET-1", {"status": "PARTIALLY_MATCHED"})
    manager.remember("BET-2", {"status": "PARTIALLY_MATCHED"})
    manager.remember("BET-3", {"status": "MATCHED"})

    status = manager.get_status()

    assert status["cached_items"] == 3
    assert status["cancel_supported"] is False
    assert status["replace_supported"] is False


def test_order_manager_cleanup_old_removes_stale_partial_fill_entries(monkeypatch):
    manager = OrderManager()

    manager.remember("OLD-PARTIAL", {"status": "PARTIALLY_MATCHED"})
    manager.remember("NEW-PARTIAL", {"status": "PARTIALLY_MATCHED"})

    manager._local_cache["OLD-PARTIAL"]["ts"] = 10.0
    manager._local_cache["NEW-PARTIAL"]["ts"] = 98.0

    monkeypatch.setattr("order_manager.time.time", lambda: 100.0)

    manager.cleanup_old(max_age_seconds=5)

    assert manager.get_cached("OLD-PARTIAL") is None
    assert manager.get_cached("NEW-PARTIAL") == {"status": "PARTIALLY_MATCHED"}