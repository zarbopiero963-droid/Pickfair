from betfair_client import BetfairClient


def test_client_initialization():
    client = BetfairClient(
        username="user",
        app_key="app",
        cert_pem="CERT",
        key_pem="KEY"
    )

    assert client.username == "user"
    assert client.app_key == "app"


def test_client_has_circuit_breaker():
    client = BetfairClient(
        username="user",
        app_key="app",
        cert_pem="CERT",
        key_pem="KEY"
    )

    assert hasattr(client, "_cb")