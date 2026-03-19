
from simulation_broker import SimulationBroker


def test_disconnect_recovery():
    broker = SimulationBroker()

    broker.connected = False

    broker.connect()

    assert broker.connected is True