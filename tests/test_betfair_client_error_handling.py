import pytest


class FakeClient:
    def place_order(self):
        raise RuntimeError("fail")


def test_error_handling_raises_runtime_error_with_expected_message():
    client = FakeClient()

    with pytest.raises(RuntimeError, match="fail"):
        client.place_order()