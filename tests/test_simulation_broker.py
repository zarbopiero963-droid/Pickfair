from simulation_broker import SimulationBroker


def test_simulation_broker_init():
    broker = SimulationBroker()

    assert broker.simulation_mode is True
    assert broker.orders == []


def test_simulation_broker_place_order():
    broker = SimulationBroker()

    broker.place_order(
        market_id="1.1",
        selection_id=10,
        side="BACK",
        price=2.0,
        stake=5.0
    )

    assert len(broker.orders) == 1