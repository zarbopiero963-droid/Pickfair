import pytest


class FakeClient:
    def place_order(self):
        raise ConnectionError("network down")


def test_network_failure_raises_connection_error_with_expected_message():
    client = FakeClient()

    with pytest.raises(ConnectionError, match="network down"):
        client.place_order()