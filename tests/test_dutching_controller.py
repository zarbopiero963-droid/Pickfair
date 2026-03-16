import pytest

from controllers.dutching_controller import DutchingController


class DummyBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


class DummySafeMode:
    def __init__(self):
        self.is_safe_mode_active = False
        self.errors = []
        self.success_count = 0

    def report_error(self, *args, **kwargs):
        self.errors.append((args, kwargs))

    def report_success(self):
        self.success_count += 1


class DummyGuardrail:
    def full_check(self, **kwargs):
        return {
            "can_proceed": True,
            "level": "normal",
            "reasons": [],
            "warnings": [],
            "blocked_until": 0,
        }


@pytest.fixture
def ctrl(monkeypatch):
    controller = DutchingController(bus=DummyBus(), simulation=False)

    controller.safe_mode = DummySafeMode()
    controller.guardrail = DummyGuardrail()

    monkeypatch.setattr(
        controller,
        "check_guardrail",
        lambda **kwargs: {
            "can_proceed": True,
            "level": "normal",
            "reasons": [],
            "warnings": [],
            "blocked_until": 0,
        },
    )

    monkeypatch.setattr(
        controller,
        "preflight_check",
        lambda selections, total_stake, mode="BACK": type(
            "PF",
            (),
            {
                "is_valid": True,
                "warnings": [],
                "errors": [],
                "details": {},
                "liquidity_ok": True,
                "liquidity_guard_ok": True,
                "spread_ok": True,
                "stake_ok": True,
                "price_ok": True,
                "book_ok": True,
            },
        )(),
    )

    monkeypatch.setattr(controller, "_check_liquidity_guard", lambda *a, **k: (True, []))

    return controller


def test_dutching_controller_safe_init(ctrl):
    assert isinstance(ctrl, DutchingController)
    assert ctrl.bus is not None
    assert ctrl.simulation is False
    assert ctrl.safe_mode.is_safe_mode_active is False


def test_dutching_controller_submit_validation_fails_for_invalid_selection(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "price": 1.0}],
        total_stake=10.0,
    )

    assert res["status"] == "VALIDATION_FAILED"
    assert res["orders"] == []
    assert "prezzo non valido" in res["errors"][0]


def test_dutching_controller_dry_run_returns_real_payload(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "runnerName": "Runner A", "price": 2.0}],
        total_stake=10.0,
        dry_run=True,
    )

    assert res["status"] == "DRY_RUN"
    assert len(res["orders"]) == 1
    assert res["orders"][0]["status"] == "DRY_RUN"
    assert res["orders"][0]["selectionId"] == 1

    payload = res["payload"]
    assert payload["source"] == "DUTCHING_CONTROLLER"
    assert payload["market_id"] == "1.1"
    assert payload["market_type"] == "MATCH_ODDS"
    assert payload["bet_type"] == "BACK"
    assert payload["simulation_mode"] is False
    assert isinstance(payload["analytics"]["potential_profit"], (int, float))
    assert isinstance(payload["analytics"]["implied_probability"], (int, float))


def test_dutching_controller_publish_bus_with_valid_payload(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "runnerName": "Runner A", "price": 2.0}],
        total_stake=10.0,
        mode="BACK",
    )

    assert res["status"] == "SUBMITTED"
    assert res["async"] is True
    assert len(ctrl.bus.events) == 1

    event_name, payload = ctrl.bus.events[0]
    assert event_name == "REQ_PLACE_DUTCHING"
    assert payload["source"] == "DUTCHING_CONTROLLER"
    assert payload["market_id"] == "1.1"
    assert payload["market_type"] == "MATCH_ODDS"
    assert payload["bet_type"] == "BACK"
    assert payload["total_stake"] == 10.0
    assert payload["results"][0]["selectionId"] == 1


def test_dutching_controller_casts_numeric_inputs_in_payload(ctrl):
    res = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": "1", "runnerName": "Runner A", "price": "2.5"}],
        total_stake="15.0",
        mode="BACK",
        dry_run=True,
    )

    assert res["status"] == "DRY_RUN"
    assert isinstance(res["payload"]["total_stake"], float)
    assert res["payload"]["total_stake"] == 15.0
    assert res["payload"]["results"][0]["selectionId"] == "1"
    assert float(res["payload"]["results"][0]["price"]) == 2.5


def test_dutching_controller_blocks_when_safe_mode_is_active(ctrl):
    ctrl.safe_mode.is_safe_mode_active = True

    with pytest.raises(RuntimeError, match="SAFE MODE attivo"):
        ctrl.submit_dutching(
            market_id="1.1",
            market_type="MATCH_ODDS",
            selections=[{"selectionId": 1, "runnerName": "Runner A", "price": 2.0}],
            total_stake=10.0,
        )