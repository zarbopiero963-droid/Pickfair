from controllers.dutching_controller import DutchingController


class DummyBus:
    def __init__(self):
        self.last_event = None
        self.last_payload = None

    def publish(self, event, payload):
        self.last_event = event
        self.last_payload = payload


def test_dutching_controller_publish_payload():
    bus = DummyBus()

    ctrl = DutchingController(bus=bus, simulation=False)

    ctrl.current_event_name = "Juve - Milan"
    ctrl.current_market_name = "Match Odds"

    ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[
            {
                "selectionId": 101,
                "runnerName": "Juve",
                "price": 2.0,
                "stake": 10.0,
            }
        ],
        total_stake=10.0,
        mode="BACK",
    )

    assert bus.last_event == "REQ_PLACE_DUTCHING"

    payload = bus.last_payload

    assert payload["source"] == "DUTCHING_CONTROLLER"
    assert payload["market_id"] == "1.1"
    assert payload["market_type"] == "MATCH_ODDS"
    assert isinstance(payload["results"], list)