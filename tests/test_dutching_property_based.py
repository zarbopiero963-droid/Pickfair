import random
from dutching import calculate_dutching_stakes


def test_dutching_randomized_inputs():
    for _ in range(100):

        selections = [
            {"selectionId": i, "price": random.uniform(1.5, 10)}
            for i in range(3)
        ]

        result, profit, book = calculate_dutching_stakes(
            selections,
            total_stake=100,
            bet_type="BACK",
            commission=5
        )

        total = sum(x["stake"] for x in result)

        assert round(total, 2) == 100
        assert all(x["stake"] >= 0 for x in result)