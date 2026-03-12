from dutching import calculate_dutching_stakes


def test_dutching_total_stake_respected():
    selections = [
        {"selectionId": 1, "runnerName": "A", "price": 2.0},
        {"selectionId": 2, "runnerName": "B", "price": 3.0},
        {"selectionId": 3, "runnerName": "C", "price": 5.0},
    ]

    results, _, _ = calculate_dutching_stakes(
        selections=selections,
        total_stake=100.0,
        bet_type="BACK",
    )

    total = sum(r["stake"] for r in results)
    assert abs(total - 100.0) <= 0.05


def test_dutching_all_stakes_positive():
    selections = [
        {"selectionId": 1, "runnerName": "A", "price": 1.50},
        {"selectionId": 2, "runnerName": "B", "price": 8.00},
    ]

    results, _, _ = calculate_dutching_stakes(
        selections=selections,
        total_stake=25.0,
        bet_type="BACK",
    )

    assert results
    for row in results:
        assert row["stake"] > 0