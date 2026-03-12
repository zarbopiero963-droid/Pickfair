from order_manager import OrderManager


class DummyApp:
    def __init__(self):
        self.bus = object()
        self.db = object()


def test_order_manager_status_and_cache_lifecycle():
    om = OrderManager(app=DummyApp())

    status = om.get_status()
    assert status["bus_available"] is True
    assert status["db_available"] is True
    assert status["cancel_supported"] is False
    assert status["replace_supported"] is False

    om.remember("abc", {"betId": "B1"})
    assert om.get_cached("abc") == {"betId": "B1"}

    om.forget("abc")
    assert om.get_cached("abc") is None


def test_order_manager_cancel_and_replace_are_explicitly_unsupported():
    om = OrderManager(app=DummyApp())
    assert om.cancel_order("1.1", "BET1") is False
    assert om.replace_order("1.1", "BET1", 2.5) is False


def test_order_manager_cleanup_old_removes_expired_items(monkeypatch):
    om = OrderManager(app=DummyApp())
    om.remember("old", {"x": 1})
    om._local_cache["old"]["ts"] = 1.0

    monkeypatch.setattr("order_manager.time.time", lambda: 9999.0)
    om.cleanup_old(max_age_seconds=10)
    assert om.get_cached("old") is None
