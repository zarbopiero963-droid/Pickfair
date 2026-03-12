from betfair_client import BetfairClient


class DummyAPI:
    def place_order(self, *args, **kwargs):
        raise ConnectionError("network failure")


def test_client_handles_network_failure():
    client = BetfairClient()

    client.api = DummyAPI()

    try:
        client.place_order(
            market_id="1.1",
            selection_id=101,
            price=2.0,
            stake=10,
            side="BACK",
        )
    except Exception:
        assert True
    else:
        assert False