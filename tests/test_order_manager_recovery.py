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


def test_order_manager_cleanup_old_behaves_like_safe_recovery_of_legacy_cache(monkeypatch):
    manager = OrderManager()

    manager.remember("expired_1", {"status": "PENDING"})
    manager.remember("expired_2", {"status": "MATCHED"})
    manager.remember("recent", {"status": "QUEUED"})

    manager._local_cache["expired_1"]["ts"] = 1.0
    manager._local_cache["expired_2"]["ts"] = 2.0
    manager._local_cache["recent"]["ts"] = 99.0

    monkeypatch.setattr("order_manager.time.time", lambda: 100.0)

    manager.cleanup_old(max_age_seconds=10)

    assert manager.get_cached("expired_1") is None
    assert manager.get_cached("expired_2") is None
    assert manager.get_cached("recent") == {"status": "QUEUED"}


def test_order_manager_status_reflects_dependencies_and_cache_count():
    class DummyApp:
        def __init__(self):
            self.bus = object()
            self.db = object()

    manager = OrderManager(app=DummyApp())

    manager.remember("k1", {"a": 1})
    manager.remember("k2", {"b": 2})

    status = manager.get_status()

    assert status["bus_available"] is True
    assert status["db_available"] is True
    assert status["cached_items"] == 2
    assert status["cancel_supported"] is False
    assert status["replace_supported"] is False


def test_order_manager_forget_missing_key_is_safe():
    manager = OrderManager()

    manager.remember("existing", {"v": 1})
    manager.forget("missing")

    assert manager.get_cached("existing") == {"v": 1}