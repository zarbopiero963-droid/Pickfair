from controllers.dutching_controller import DutchingController


class DummyBus:
    def __init__(self):
        self.events = []

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))


class DummySafeMode:
    def __init__(self):
        self.is_safe_mode_active = False

    def report_error(self, *args, **kwargs):
        return None

    def report_success(self):
        return None


class DummyGuardrail:
    def full_check(self, **kwargs):
        return {
            "can_proceed": True,
            "level": "normal",
            "reasons": [],
            "warnings": [],
            "blocked_until": 0,
        }


def _build_controller(monkeypatch):
    bus = DummyBus()
    controller = DutchingController(bus=bus, simulation=False)

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

    return controller, bus


def test_controller_publish_payload_contains_core_runtime_fields(monkeypatch):
    controller, bus = _build_controller(monkeypatch)

    res = controller.submit_dutching(
        market_id="1.123",
        market_type="MATCH_ODDS",
        event_name="Juve - Milan",
        market_name="Match Odds",
        selections=[
            {"selectionId": 11, "runnerName": "Juve", "price": 2.0},
            {"selectionId": 22, "runnerName": "Milan", "price": 3.0},
        ],
        total_stake=15.0,
        mode="BACK",
    )

    assert res["status"] == "SUBMITTED"
    assert len(bus.events) == 1

    event_name, payload = bus.events[0]

    assert event_name == "REQ_PLACE_DUTCHING"
    assert payload["source"] == "DUTCHING_CONTROLLER"
    assert payload["market_id"] == "1.123"
    assert payload["market_type"] == "MATCH_ODDS"
    assert payload["event_name"] == "Juve - Milan"
    assert payload["market_name"] == "Match Odds"
    assert payload["bet_type"] == "BACK"
    assert payload["total_stake"] == 15.0
    assert isinstance(payload["results"], list)
    assert len(payload["results"]) == 2


def test_controller_publish_payload_contains_preflight_and_analytics(monkeypatch):
    controller, bus = _build_controller(monkeypatch)

    controller.submit_dutching(
        market_id="1.456",
        market_type="MATCH_ODDS",
        selections=[
            {"selectionId": 11, "runnerName": "Home", "price": 2.5},
        ],
        total_stake=10.0,
        dry_run=True,
    )

    payload = bus.events[0][1] if bus.events else None

    if payload is None:
        dry_run = controller.submit_dutching(
            market_id="1.456",
            market_type="MATCH_ODDS",
            selections=[
                {"selectionId": 11, "runnerName": "Home", "price": 2.5},
            ],
            total_stake=10.0,
            mode="BACK",
        )
        payload = dry_run["payload"] if "payload" in dry_run else bus.events[-1][1]

    assert "preflight" in payload
    assert "analytics" in payload
    assert payload["preflight"]["is_valid"] is True
    assert isinstance(payload["preflight"]["warnings"], list)
    assert isinstance(payload["preflight"]["errors"], list)
    assert isinstance(payload["analytics"]["potential_profit"], int | float)
    assert isinstance(payload["analytics"]["implied_probability"], int | float)


def test_controller_publish_payload_casts_selection_rows_consistently(monkeypatch):
    controller, bus = _build_controller(monkeypatch)

    controller.submit_dutching(
        market_id="1.789",
        market_type="MATCH_ODDS",
        selections=[
            {"selectionId": "11", "runnerName": "Alpha", "price": "2.2"},
            {"selectionId": "22", "runnerName": "Beta", "price": "4.4"},
        ],
        total_stake="20.0",
        mode="BACK",
    )

    payload = bus.events[-1][1]

    assert float(payload["total_stake"]) == 20.0
    assert len(payload["results"]) == 2
    assert payload["results"][0]["selectionId"] == "11"
    assert float(payload["results"][0]["price"]) == 2.2
    assert payload["results"][1]["selectionId"] == "22"
    assert float(payload["results"][1]["price"]) == 4.4


def test_controller_publish_payload_keeps_simulation_flag(monkeypatch):
    bus = DummyBus()
    controller = DutchingController(bus=bus, simulation=True)

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

    controller.submit_dutching(
        market_id="1.999",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "runnerName": "Runner", "price": 2.0}],
        total_stake=5.0,
        mode="BACK",
    )

    payload = bus.events[-1][1]

    assert payload["simulation_mode"] is True