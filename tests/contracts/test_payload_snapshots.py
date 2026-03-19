from copy import deepcopy

from tests.fixtures.system_payloads import SYSTEM_PAYLOAD

REQUIRED_TOP_LEVEL_KEYS = [
    "source",
    "market_id",
    "market_type",
    "event_name",
    "market_name",
    "results",
    "bet_type",
    "total_stake",
    "use_best_price",
    "simulation_mode",
    "auto_green",
    "stop_loss",
    "take_profit",
    "trailing",
    "preflight",
    "analytics",
]

REQUIRED_RESULT_KEYS = [
    "selectionId",
    "runnerName",
    "price",
    "stake",
    "side",
    "effectiveType",
]

REQUIRED_PREFLIGHT_KEYS = ["is_valid", "warnings", "errors", "details"]
REQUIRED_ANALYTICS_KEYS = ["potential_profit", "implied_probability"]


def test_system_payload_top_level_contract():
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in SYSTEM_PAYLOAD, f"Missing top-level key: {key}"


def test_system_payload_core_types():
    assert isinstance(SYSTEM_PAYLOAD["source"], str)
    assert SYSTEM_PAYLOAD["source"].strip()

    assert isinstance(SYSTEM_PAYLOAD["market_id"], str)
    assert SYSTEM_PAYLOAD["market_id"].strip()

    assert isinstance(SYSTEM_PAYLOAD["market_type"], str)
    assert SYSTEM_PAYLOAD["market_type"].strip()

    assert isinstance(SYSTEM_PAYLOAD["results"], list)
    assert isinstance(SYSTEM_PAYLOAD["total_stake"], int | float)
    assert isinstance(SYSTEM_PAYLOAD["preflight"], dict)
    assert isinstance(SYSTEM_PAYLOAD["analytics"], dict)


def test_system_payload_result_contract():
    assert SYSTEM_PAYLOAD["results"], "results must contain at least one selection row"

    row = SYSTEM_PAYLOAD["results"][0]

    for key in REQUIRED_RESULT_KEYS:
        assert key in row, f"Missing result key: {key}"

    assert isinstance(row["selectionId"], int)
    assert isinstance(row["runnerName"], str)
    assert row["runnerName"].strip()

    assert isinstance(row["price"], int | float)
    assert row["price"] > 1.0

    assert isinstance(row["stake"], int | float)
    assert row["stake"] > 0

    assert row["side"] in {"BACK", "LAY"}
    assert row["effectiveType"] in {"BACK", "LAY"}


def test_system_payload_preflight_contract():
    preflight = SYSTEM_PAYLOAD["preflight"]

    for key in REQUIRED_PREFLIGHT_KEYS:
        assert key in preflight, f"Missing preflight key: {key}"

    assert isinstance(preflight["is_valid"], bool)
    assert isinstance(preflight["warnings"], list)
    assert isinstance(preflight["errors"], list)
    assert isinstance(preflight["details"], dict)


def test_system_payload_analytics_contract():
    analytics = SYSTEM_PAYLOAD["analytics"]

    for key in REQUIRED_ANALYTICS_KEYS:
        assert key in analytics, f"Missing analytics key: {key}"

    assert isinstance(analytics["potential_profit"], int | float)
    assert analytics["potential_profit"] >= 0

    assert isinstance(analytics["implied_probability"], int | float)
    assert 0 <= analytics["implied_probability"] <= 1


def test_system_payload_total_stake_matches_result_rows():
    row_stake_total = sum(float(row["stake"]) for row in SYSTEM_PAYLOAD["results"])
    assert row_stake_total == float(SYSTEM_PAYLOAD["total_stake"])


def test_system_payload_valid_preflight_has_no_errors():
    preflight = SYSTEM_PAYLOAD["preflight"]

    if preflight["is_valid"]:
        assert preflight["errors"] == []


def test_system_payload_is_not_mutated_by_validation():
    original = deepcopy(SYSTEM_PAYLOAD)

    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in SYSTEM_PAYLOAD

    assert SYSTEM_PAYLOAD == original