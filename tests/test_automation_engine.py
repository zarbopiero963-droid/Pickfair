from automation_engine import AutomationEngine


def test_automation_engine_initialization():
    engine = AutomationEngine()

    assert engine.running is False
    assert isinstance(engine.rules, list)


def test_automation_engine_start_stop():
    engine = AutomationEngine()

    engine.start()
    assert engine.running is True

    engine.stop()
    assert engine.running is False