import pytest

from automation_optimizer import AutomationOptimizer


def test_optimizer_init():
    opt = AutomationOptimizer()

    assert opt is not None