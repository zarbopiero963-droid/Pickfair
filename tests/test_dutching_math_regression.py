from dutching import calculate_dutching_stakes


def test_dutching_total_stake_respected():
    selections = [
        {"selectionId": 1, "runnerName": "A", "price": 2.0},
        {"selectionId": 2, "runnerName": "B", "price": 3.0},
        {"selectionId": 3, "runnerName": "C", "price": 5.0},
    ]

    results, _, _ = calculate_dutching_stakes(
        selections,
        total_stake=100,
        bet_type="BACK",
    )

    total = sum(r["stake"] for r in results)

    assert abs(total - 100) < 0.1


def test_dutching_no_negative_stakes():
    selections = [
        {"selectionId": 1, "runnerName": "A", "price": 1.5},
        {"selectionId": 2, "runnerName": "B", "price": 10.0},
    ]

    results, _, _ = calculate_dutching_stakes(selections, 50)

    for r in results:
        assert r["stake"] > 0