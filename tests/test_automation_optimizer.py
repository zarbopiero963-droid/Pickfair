from automation_optimizer import AutomationOptimizer


def test_optimizer_initial_state():
    opt = AutomationOptimizer()

    assert opt.enabled is True
    assert isinstance(opt.history, list)


def test_optimizer_records_result():
    opt = AutomationOptimizer()

    opt.record_result(True)
    opt.record_result(False)

    assert len(opt.history) == 2
    assert opt.history[0] is True
    assert opt.history[1] is False