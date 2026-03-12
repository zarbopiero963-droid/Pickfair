import pytest


class FakeClient:
    def place_order(self):
        raise ConnectionError("network down")


def test_network_failure():
    client = FakeClient()

    with pytest.raises(ConnectionError):
        client.place_order()