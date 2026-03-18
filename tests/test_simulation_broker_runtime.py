from simulation_broker import SimulationBroker


def test_simulation_place_bet():
    broker = SimulationBroker()

    result = broker.place_bet(
        market_id="1.100",
        selection_id=10,
        side="BACK",
        price=2.0,
        size=5.0,
    )

    assert result["status"] == "SUCCESS"


def test_simulation_balance_updates():
    broker = SimulationBroker(initial_balance=100)

    broker.place_bet(
        market_id="1.200",
        selection_id=20,
        side="BACK",
        price=2.0,
        size=10,
    )

    assert broker.balance <= 100


def test_simulation_cancel_order():
    broker = SimulationBroker()

    broker.place_bet(
        market_id="1.300",
        selection_id=30,
        side="BACK",
        price=2.0,
        size=5,
    )

    result = broker.cancel_orders(market_id="1.300")

    assert result["status"] == "SUCCESS"


def test_simulation_orders_tracking():
    broker = SimulationBroker()

    broker.place_bet(
        market_id="1.400",
        selection_id=40,
        side="BACK",
        price=2.0,
        size=5,
    )

    orders = broker.get_current_orders()

    assert isinstance(orders, dict)