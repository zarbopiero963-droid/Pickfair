import pytest

from controllers.dutching_controller import DutchingController


class DummyBus:
    def publish(self, event, payload):
        self.last_event = event
        self.last_payload = payload


@pytest.fixture
def ctrl():
    return DutchingController(bus=DummyBus(), simulation=False)


def test_dutching_controller_safe_init(ctrl):
    assert isinstance(ctrl, DutchingController)
    assert isinstance(ctrl.bus, DummyBus)
    assert ctrl.simulation is False


def test_dutching_controller_submit_validation_fails(ctrl):
    res = ctrl.submit_dutching(
        "1.1",
        "MATCH_ODDS",
        [{"selectionId": 1, "price": 1.0}],
        10.0,
    )

    assert res["status"] == "VALIDATION_FAILED"


def test_dutching_controller_dry_run(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "price": 2.0}],
        total_stake=10.0,
        dry_run=True,
    )

    assert res["status"] == "DRY_RUN"
    assert len(res["orders"]) == 1


def test_dutching_controller_publish_bus(ctrl):
    ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "price": 2.0, "stake": 10.0}],
        total_stake=10.0,
        mode="BACK",
    )

    assert hasattr(ctrl.bus, "last_event")
    assert ctrl.bus.last_event == "REQ_PLACE_DUTCHING"
    assert ctrl.bus.last_payload["source"] == "DUTCHING_CONTROLLER"


def test_dutching_controller_float_casting_returns_real_dry_run_payload(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": "1", "price": "2.5", "stake": "15.0"}],
        total_stake="15.0",
        mode="BACK",
        dry_run=True,
    )

    assert res["status"] == "DRY_RUN"
    assert len(res["orders"]) == 1
    assert res["orders"][0]["status"] == "DRY_RUN"
    assert isinstance(res["payload"]["total_stake"], float)
    assert res["payload"]["total_stake"] == 15.0