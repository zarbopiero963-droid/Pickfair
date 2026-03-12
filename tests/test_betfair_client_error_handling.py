import pytest


class FakeClient:
    def place_order(self):
        raise RuntimeError("fail")


def test_error_handling():
    client = FakeClient()

    with pytest.raises(RuntimeError):
        client.place_order()