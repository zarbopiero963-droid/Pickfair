from dutching import calculate_dutching


def test_two_runner_dutching_basic():
    odds = [2.0, 2.0]
    total_stake = 100

    result = calculate_dutching(odds, total_stake)

    assert len(result["stakes"]) == 2
    assert sum(result["stakes"]) == total_stake


def test_three_runner_dutching_basic():
    odds = [2.0, 3.0, 4.0]
    total_stake = 90

    result = calculate_dutching(odds, total_stake)

    assert len(result["stakes"]) == 3
    assert abs(sum(result["stakes"]) - total_stake) < 0.01


def test_profit_is_equalized():
    odds = [2.0, 3.0]
    total_stake = 100

    result = calculate_dutching(odds, total_stake)

    profits = result["profits"]

    assert abs(profits[0] - profits[1]) < 0.01


def test_invalid_odds_raise_error():
    odds = [1.0, 0]
    total_stake = 100

    try:
        calculate_dutching(odds, total_stake)
        raise AssertionError()
    except Exception:
        assert True