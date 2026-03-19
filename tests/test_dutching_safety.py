import math

from core.event_bus import EventBus
from core.risk_middleware import RiskMiddleware
from dutching import calculate_dutching_stakes


def test_dutching_back_math_preserves_total_stake():
    selections = [
        {"selectionId": 1, "price": 1.50, "runnerName": "A"},
        {"selectionId": 2, "price": 3.00, "runnerName": "B"},
    ]

    results, profit, implied_prob = calculate_dutching_stakes(
        selections,
        10.0,
        "BACK",
    )

    total_calculated = sum(float(r["stake"]) for r in results)

    assert math.isclose(total_calculated, 10.0, abs_tol=0.02)
    assert len(results) == 2
    assert all(float(r["stake"]) > 0 for r in results)
    assert isinstance(profit, int | float)
    assert isinstance(implied_prob, int | float)


def test_dutching_lay_math_returns_positive_stakes():
    selections = [
        {"selectionId": 1, "price": 1.10, "runnerName": "Fav"},
        {"selectionId": 2, "price": 1.20, "runnerName": "Outsider"},
    ]

    results, profit, implied_prob = calculate_dutching_stakes(
        selections,
        5.0,
        "LAY",
    )

    assert len(results) == 2
    assert all(float(r["stake"]) > 0 for r in results)
    assert all(float(r["price"]) > 1.0 for r in results)
    assert isinstance(profit, int | float)
    assert isinstance(implied_prob, int | float)


def test_risk_middleware_forwards_only_one_duplicate_request():
    bus = EventBus()
    RiskMiddleware(bus, None, None)

    published = []
    bus.subscribe("CMD_PLACE_DUTCHING", lambda payload: published.append(payload))

    payload = {
        "market_id": "1.123",
        "market_type": "MATCH_ODDS",
        "event_name": "Test Event",
        "market_name": "Test Market",
        "results": [
            {"selectionId": 1, "stake": 5.0, "price": 2.0, "runnerName": "A"}
        ],
        "bet_type": "BACK",
        "total_stake": 5.0,
        "use_best_price": False,
        "simulation_mode": False,
        "source": "TEST",
    }

    bus.publish("REQ_PLACE_DUTCHING", payload)
    bus.publish("REQ_PLACE_DUTCHING", payload)

    assert len(published) == 1
    assert published[0]["market_id"] == "1.123"
    assert published[0]["bet_type"] == "BACK"

