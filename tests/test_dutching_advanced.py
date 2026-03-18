from dutching import calculate_dutching_stakes


def test_dutching_single_runner_edge_case():
    selections = [{"selectionId": 1, "price": 2.0}]

    result, profit, book = calculate_dutching_stakes(
        selections,
        total_stake=50,
        bet_type="BACK",
        commission=5
    )

    assert result[0]["stake"] == 50


def test_dutching_many_runners():
    selections = [{"selectionId": i, "price": 2 + i} for i in range(10)]

    result, profit, book = calculate_dutching_stakes(
        selections,
        total_stake=200,
        bet_type="BACK",
        commission=5
    )

    assert len(result) == 10