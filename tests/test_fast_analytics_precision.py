import math
import random

import pytest

from core.fast_analytics import FastWoMState


def _sum_ticks(state):
    expected_back = math.fsum(t["back_volume"] for t in state.ticks)
    expected_lay = math.fsum(t["lay_volume"] for t in state.ticks)
    return expected_back, expected_lay


def test_running_sums_match_window_after_many_pushes():
    state = FastWoMState(max_ticks=50)

    for _ in range(5000):
        state.push({"back_volume": 0.1, "lay_volume": 0.1})

    expected_back, expected_lay = _sum_ticks(state)

    assert state.sum_back == pytest.approx(expected_back, abs=1e-12)
    assert state.sum_lay == pytest.approx(expected_lay, abs=1e-12)


def test_eviction_recompute_keeps_internal_sums_aligned():
    state = FastWoMState(max_ticks=10)

    for _ in range(10):
        state.push({"back_volume": 0.1, "lay_volume": 0.1})

    for _ in range(2000):
        state.push({"back_volume": 0.1, "lay_volume": 0.1})

    expected_back, expected_lay = _sum_ticks(state)

    assert state.sum_back == pytest.approx(expected_back, abs=1e-12)
    assert state.sum_lay == pytest.approx(expected_lay, abs=1e-12)


def test_sums_never_go_negative_under_repeated_small_updates():
    state = FastWoMState(max_ticks=20)

    for _ in range(3000):
        state.push({"back_volume": 0.1, "lay_volume": 0.1})

    assert state.sum_back >= 0.0
    assert state.sum_lay >= 0.0


def test_wom_remains_neutral_for_balanced_flow_after_many_updates():
    state = FastWoMState(max_ticks=50)

    for _ in range(5000):
        state.push({"back_volume": 1.0, "lay_volume": 1.0})

    assert state.wom() == pytest.approx(0.5, abs=1e-12)

    if hasattr(state, "imbalance"):
        assert state.imbalance() == pytest.approx(0.0, abs=1e-12)


def test_random_window_matches_recomputed_ground_truth():
    state = FastWoMState(max_ticks=30)
    rng = random.Random(1337)

    for _ in range(3000):
        state.push(
            {
                "back_volume": rng.uniform(0.01, 5.0),
                "lay_volume": rng.uniform(0.01, 5.0),
            }
        )

    expected_back, expected_lay = _sum_ticks(state)

    assert state.sum_back == pytest.approx(expected_back, abs=1e-12)
    assert state.sum_lay == pytest.approx(expected_lay, abs=1e-12)


def test_outputs_match_window_ground_truth_after_heavy_eviction():
    state = FastWoMState(max_ticks=25)

    for i in range(4000):
        state.push(
            {
                "back_volume": 0.1 if i % 2 == 0 else 0.2,
                "lay_volume": 0.2 if i % 2 == 0 else 0.1,
            }
        )

    expected_back, expected_lay = _sum_ticks(state)
    total = expected_back + expected_lay

    expected_wom = 0.5 if total <= 0 else expected_back / total
    expected_imbalance = 0.0 if total <= 0 else (expected_back - expected_lay) / total

    assert state.sum_back == pytest.approx(expected_back, abs=1e-12)
    assert state.sum_lay == pytest.approx(expected_lay, abs=1e-12)
    assert state.wom() == pytest.approx(expected_wom, abs=1e-12)

    if hasattr(state, "imbalance"):
        assert state.imbalance() == pytest.approx(expected_imbalance, abs=1e-12)
