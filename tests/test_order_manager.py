import time

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
    assert status["mode"] == "compatibility_layer_only"
    assert status["cached_items"] == 0

    om.remember("abc", {"betId": "B1"})
    assert om.get_cached("abc") == {"betId": "B1"}
    assert om.get_status()["cached_items"] == 1

    om.forget("abc")
    assert om.get_cached("abc") is None
    assert om.get_status()["cached_items"] == 0


def test_order_manager_cancel_and_replace_are_explicitly_unsupported():
    om = OrderManager(app=DummyApp())

    assert om.cancel_order("1.1", "BET1") is False
    assert om.replace_order("1.1", "BET1", 2.5) is False


def test_order_manager_cleanup_old_removes_only_expired_items(monkeypatch):
    om = OrderManager(app=DummyApp())

    om.remember("old", {"x": 1})
    om.remember("fresh", {"x": 2})

    om._local_cache["old"]["ts"] = 10.0
    om._local_cache["fresh"]["ts"] = 95.0

    monkeypatch.setattr("order_manager.time.time", lambda: 100.0)

    om.cleanup_old(max_age_seconds=20)

    assert om.get_cached("old") is None
    assert om.get_cached("fresh") == {"x": 2}
    assert om.get_status()["cached_items"] == 1


def test_order_manager_get_cached_returns_default_when_missing():
    om = OrderManager(app=DummyApp())

    default_value = {"fallback": True}

    assert om.get_cached("missing", default=default_value) == default_value


def test_order_manager_clear_removes_entire_cache():
    om = OrderManager(app=DummyApp())

    om.remember("a", {"v": 1})
    om.remember("b", {"v": 2})

    assert om.get_status()["cached_items"] == 2

    om.clear()

    assert om.get_status()["cached_items"] == 0
    assert om.get_cached("a") is None
    assert om.get_cached("b") is None


def test_order_manager_remember_overwrites_same_key_with_latest_payload():
    om = OrderManager(app=DummyApp())

    om.remember("same", {"value": 1})
    first_ts = om._local_cache["same"]["ts"]

    time.sleep(0.001)
    om.remember("same", {"value": 2})
    second_ts = om._local_cache["same"]["ts"]

    assert om.get_cached("same") == {"value": 2}
    assert second_ts >= first_ts