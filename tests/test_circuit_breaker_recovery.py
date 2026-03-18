import time
from circuit_breaker import CircuitBreaker


def test_circuit_breaker_recovers():

    cb = CircuitBreaker(failure_threshold=2, recovery_time=0.1)

    cb.record_failure()
    cb.record_failure()

    assert cb.is_open()

    time.sleep(0.2)

    assert cb.is_half_open() or not cb.is_open()