from controllers.dutching_controller import DutchingController


class DummyBus:
    def __init__(self):
        self.events = []

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))


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


def _build_controller(monkeypatch, simulation=False):
    controller = DutchingController(bus=DummyBus(), simulation=simulation)
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


def test_controller_submit_returns_expected_contract_keys(monkeypatch):
    controller = _build_controller(monkeypatch)

    res = controller.submit_dutching(
        market_id="1.111",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 1, "runnerName": "A", "price": 2.0}],
        total_stake=10.0,
        mode="BACK",
    )

    assert "status" in res
    assert "orders" in res
    assert "async" in res
    assert res["status"] == "SUBMITTED"
    assert isinstance(res["orders"], list)
    assert res["async"] is True


def test_controller_dry_run_contract_contains_payload_and_order_rows(monkeypatch):
    controller = _build_controller(monkeypatch)

    res = controller.submit_dutching(
        market_id="1.222",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 2, "runnerName": "B", "price": 3.0}],
        total_stake=12.0,
        mode="BACK",
        dry_run=True,
    )

    assert res["status"] == "DRY_RUN"
    assert "payload" in res
    assert "orders" in res
    assert len(res["orders"]) == 1
    assert res["orders"][0]["status"] == "DRY_RUN"
    assert res["payload"]["market_id"] == "1.222"
    assert res["payload"]["bet_type"] == "BACK"


def test_controller_validation_failure_contract_contains_errors(monkeypatch):
    controller = _build_controller(monkeypatch)

    res = controller.submit_dutching(
        market_id="1.333",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 3, "runnerName": "C", "price": 1.0}],
        total_stake=10.0,
        mode="BACK",
    )

    assert res["status"] == "VALIDATION_FAILED"
    assert "errors" in res
    assert isinstance(res["errors"], list)
    assert res["orders"] == []


def test_controller_simulation_flag_is_reflected_in_payload(monkeypatch):
    controller = _build_controller(monkeypatch, simulation=True)

    res = controller.submit_dutching(
        market_id="1.444",
        market_type="MATCH_ODDS",
        selections=[{"selectionId": 4, "runnerName": "D", "price": 2.5}],
        total_stake=5.0,
        mode="BACK",
        dry_run=True,
    )

    assert res["payload"]["simulation_mode"] is True