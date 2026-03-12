import pytest

from goal_engine_pro import GoalEnginePro


def test_goal_engine_init():
    engine = GoalEnginePro()

    assert engine is not None