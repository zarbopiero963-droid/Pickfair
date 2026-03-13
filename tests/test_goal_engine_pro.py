from goal_engine_pro import GoalEnginePro


def test_goal_engine_init():
    engine = GoalEnginePro()

    assert engine.enabled is True
    assert engine.current_goal is None


def test_goal_engine_set_goal():
    engine = GoalEnginePro()

    engine.set_goal(100)

    assert engine.current_goal == 100