import pytest

from dutching import calculate_dutching_stakes


def test_dutching_total_stake():
    selections = [
        {"selectionId": 1, "price": 2.0},
        {"selectionId": 2, "price": 3.0},
    ]

    stakes, _, _ = calculate_dutching_stakes(selections, 100, bet_type="BACK")

    total = sum(s["stake"] for s in stakes)

    assert abs(total - 100) < 0.01