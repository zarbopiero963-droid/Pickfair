import pytest

from betfair_client import BetfairClient
from circuit_breaker import TransientError


class DummyBetting:
    def place_orders(self, *args, **kwargs):
        raise ConnectionError("network failure")


class DummyClient:
    def __init__(self):
        self.betting = DummyBetting()


def test_client_place_bets_wraps_network_failure_as_transient_error():
    client = BetfairClient(
        username="user",
        app_key="app",
        cert_pem="CERT",
        key_pem="KEY",
    )
    client.client = DummyClient()

    instructions = [
        {
            "selectionId": 101,
            "side": "BACK",
            "price": 2.0,
            "size": 10.0,
        }
    ]

    with pytest.raises(TransientError, match="Errore Temporaneo"):
        client.place_bets("1.123456", instructions)

    assert client._cb.failures == 1