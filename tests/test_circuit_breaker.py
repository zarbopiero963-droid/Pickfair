from circuit_breaker import CircuitBreaker


def test_circuit_breaker_opens_after_failures():

    cb = CircuitBreaker(failure_threshold=3)

    for _ in range(3):
        cb.record_failure()

    assert cb.is_open()