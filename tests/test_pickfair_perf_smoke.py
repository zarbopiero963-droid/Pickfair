import time

from dutching import calculate_dutching_stakes, dynamic_cashout_single


def test_perf_dutching_100_cycles():
    selections = [
        {"selectionId": 1, "runnerName": "A", "price": 2.0},
        {"selectionId": 2, "runnerName": "B", "price": 3.0},
        {"selectionId": 3, "runnerName": "C", "price": 4.0},
    ]

    start = time.perf_counter()
    for _ in range(100):
        results, profit, implied_prob = calculate_dutching_stakes(
            selections=selections,
            total_stake=100.0,
            bet_type="BACK",
        )
        assert len(results) == 3
    elapsed = time.perf_counter() - start

    assert elapsed < 0.30


def test_perf_cashout_1000_cycles():
    start = time.perf_counter()
    for _ in range(1000):
        result = dynamic_cashout_single(
            back_stake=20.0,
            back_price=8.0,
            lay_price=7.0,
            commission=4.5,
        )
        assert "lay_stake" in result
    elapsed = time.perf_counter() - start

    assert elapsed < 0.20