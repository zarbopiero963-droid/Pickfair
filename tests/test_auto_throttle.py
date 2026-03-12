import pytest

from auto_throttle import AutoThrottle


def test_auto_throttle_basic():
    throttle = AutoThrottle()

    assert throttle is not None