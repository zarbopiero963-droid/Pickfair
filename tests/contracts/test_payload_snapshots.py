from tests.fixtures.system_payloads import SYSTEM_PAYLOAD


def test_system_payload_top_level_contract():
    required = [
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

    for key in required:
        assert key in SYSTEM_PAYLOAD


def test_system_payload_core_types():
    assert isinstance(SYSTEM_PAYLOAD["source"], str)
    assert isinstance(SYSTEM_PAYLOAD["market_id"], str)
    assert isinstance(SYSTEM_PAYLOAD["market_type"], str)
    assert isinstance(SYSTEM_PAYLOAD["results"], list)
    assert isinstance(SYSTEM_PAYLOAD["total_stake"], (int, float))
    assert isinstance(SYSTEM_PAYLOAD["preflight"], dict)
    assert isinstance(SYSTEM_PAYLOAD["analytics"], dict)


def test_system_payload_result_contract():
    assert len(SYSTEM_PAYLOAD["results"]) >= 1

    row = SYSTEM_PAYLOAD["results"][0]

    required = [
        "selectionId",
        "runnerName",
        "price",
        "stake",
        "side",
        "effectiveType",
    ]
    for key in required:
        assert key in row

    assert isinstance(row["selectionId"], int)
    assert isinstance(row["runnerName"], str)
    assert isinstance(row["price"], (int, float))
    assert isinstance(row["stake"], (int, float))
    assert row["side"] in {"BACK", "LAY"}
    assert row["effectiveType"] in {"BACK", "LAY"}


def test_system_payload_preflight_contract():
    preflight = SYSTEM_PAYLOAD["preflight"]

    required = ["is_valid", "warnings", "errors", "details"]
    for key in required:
        assert key in preflight

    assert isinstance(preflight["is_valid"], bool)
    assert isinstance(preflight["warnings"], list)
    assert isinstance(preflight["errors"], list)
    assert isinstance(preflight["details"], dict)


def test_system_payload_analytics_contract():
    analytics = SYSTEM_PAYLOAD["analytics"]

    required = ["potential_profit", "implied_probability"]
    for key in required:
        assert key in analytics

    assert isinstance(analytics["potential_profit"], (int, float))
    assert isinstance(analytics["implied_probability"], (int, float))
