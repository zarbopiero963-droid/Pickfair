from order_manager import OrderManager


class DummyBroker:
    def place_order(self, order):
        return {"status": "SUCCESS", "betId": "123"}


def test_order_manager_place_order_success():
    broker = DummyBroker()

    manager = OrderManager(broker=broker)

    order = {
        "selectionId": 101,
        "price": 2.0,
        "stake": 10.0,
        "side": "BACK",
    }

    result = manager.place_order(order)

    assert result["status"] == "SUCCESS"
    assert "betId" in result


def test_order_manager_handles_invalid_order():
    broker = DummyBroker()
    manager = OrderManager(broker=broker)

    invalid_order = {}

    try:
        manager.place_order(invalid_order)
    except Exception:
        assert True
    else:
        assert False