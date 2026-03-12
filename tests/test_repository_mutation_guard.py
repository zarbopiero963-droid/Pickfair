from dutching import calculate_dutching_stakes


def test_dutching_no_negative_stake():
    selections = [
        {"selectionId": 1, "price": 2.0},
        {"selectionId": 2, "price": 4.0},
    ]

    stakes, _, _ = calculate_dutching_stakes(selections, 100)

    for s in stakes:
        assert s["stake"] >= 0