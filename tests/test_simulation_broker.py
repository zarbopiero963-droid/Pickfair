import pytest

from simulation_broker import SimulationBroker


def test_simulation_broker_init():
    broker = SimulationBroker()

    assert broker is not None