import time

from auto_throttle import AutoThrottle


def test_auto_throttle_basic():
    throttle = AutoThrottle(max_calls=2, period=1.0)

    assert throttle.allow_call() is True
    assert throttle.allow_call() is True

    # terza chiamata dovrebbe essere bloccata
    assert throttle.allow_call() is False


def test_auto_throttle_resets_after_period():
    throttle = AutoThrottle(max_calls=1, period=0.2)

    assert throttle.allow_call() is True
    assert throttle.allow_call() is False

    time.sleep(0.25)

    assert throttle.allow_call() is True