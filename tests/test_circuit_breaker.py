import pytest

from circuit_breaker import CircuitBreaker, PermanentError, TransientError


def test_circuit_breaker_transient_errors_open_after_threshold():
    cb = CircuitBreaker(max_failures=2, reset_timeout=60)

    with pytest.raises(TransientError):
        cb.call(lambda: (_ for _ in ()).throw(Exception("timeout network")))
    assert cb.failures == 1
    assert cb.is_open() is False

    with pytest.raises(TransientError):
        cb.call(lambda: (_ for _ in ()).throw(Exception("502 gateway")))
    assert cb.is_open() is True


def test_circuit_breaker_permanent_error_does_not_count_as_transient_failure():
    cb = CircuitBreaker(max_failures=3, reset_timeout=60)

    with pytest.raises(PermanentError):
        cb.call(lambda: (_ for _ in ()).throw(Exception("insufficient_funds")))

    assert cb.failures == 0
    assert cb.is_open() is False


def test_circuit_breaker_resets_after_success():
    cb = CircuitBreaker(max_failures=3, reset_timeout=60)

    with pytest.raises(TransientError):
        cb.call(lambda: (_ for _ in ()).throw(Exception("timeout")))

    assert cb.failures == 1
    result = cb.call(lambda: "ok")
    assert result == "ok"
    assert cb.failures == 0
    assert cb.is_open() is False
