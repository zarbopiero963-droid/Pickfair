from simulation_broker import SimulationBroker


def test_sim_broker_order_storage():
    broker = SimulationBroker()

    broker.place_order("1.1", 1, "BACK", 2.0, 10.0)
    broker.place_order("1.1", 2, "LAY", 3.0, 5.0)

    assert len(broker.orders) == 2

    first = broker.orders[0]

    assert first["side"] == "BACK"
    assert first["price"] == 2.0