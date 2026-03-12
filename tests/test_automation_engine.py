import pytest

from automation_engine import AutomationEngine


class DummyController:
    pass


def test_automation_engine_init():
    engine = AutomationEngine(controller=DummyController())

    assert engine.controller is not None