from simulation_broker import SimulationBroker


def test_sim_broker_order():
    broker = SimulationBroker()

    order = broker.place_order({"price": 2.0})

    assert order is not None