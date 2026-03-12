from controllers.dutching_controller import DutchingController


class DummyBus:
    def publish(self, event_name, payload):
        self.last_event = (event_name, payload)


def test_controller_publish_payload_complete():
    bus = DummyBus()
    ctrl = DutchingController(bus=bus, simulation=False)

    ctrl.current_event_name = "Juve - Milan"
    ctrl.current_market_name = "Match Odds"

    result = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[
            {
                "selectionId": 1,
                "runnerName": "Juve",
                "price": 2.0,
                "stake": 10.0,
                "back_ladder": [{"price": 2.0, "size": 1000.0}],
                "lay_ladder": [{"price": 2.02, "size": 1000.0}],
            }
        ],
        total_stake=10.0,
        mode="BACK",
    )

    assert result["status"] == "SUBMITTED"
    assert hasattr(bus, "last_event")

    event_name, payload = bus.last_event

    assert event_name == "REQ_PLACE_DUTCHING"
    assert payload["market_id"] == "1.1"
    assert payload["market_type"] == "MATCH_ODDS"
    assert payload["event_name"] == "Juve - Milan"
    assert payload["market_name"] == "Match Odds"
    assert payload["bet_type"] == "BACK"
    assert "results" in payload
    assert "preflight" in payload
    assert "analytics" in payload