from dutching import calculate_dutching_stakes


def test_dutching_two_runner_distribution():
    selections = [
        {"selectionId": 1, "price": 2.0},
        {"selectionId": 2, "price": 3.0},
    ]

    result, profit, book = calculate_dutching_stakes(
        selections,
        total_stake=100,
        bet_type="BACK",
        commission=5
    )

    assert len(result) == 2
    assert round(sum(x["stake"] for x in result), 2) == 100


def test_dutching_high_odds():
    selections = [
        {"selectionId": 1, "price": 20},
        {"selectionId": 2, "price": 30},
    ]

    result, profit, book = calculate_dutching_stakes(
        selections,
        total_stake=50,
        bet_type="BACK",
        commission=5
    )

    assert len(result) == 2