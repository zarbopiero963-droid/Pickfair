from circuit_breaker import CircuitBreaker


def test_circuit_recovery():
    cb = CircuitBreaker(max_failures=1)

    cb.record_failure()

    assert cb.is_open()

    cb.reset()

    assert not cb.is_open()