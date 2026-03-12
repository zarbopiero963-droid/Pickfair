import pytest

from executor_manager import SafeExecutor


def test_safe_executor_submit_returns_value():
    ex = SafeExecutor(max_workers=2, default_timeout=1)
    try:
        result = ex.submit("sum", lambda a, b: a + b, 2, 3)
        assert result == 5
    finally:
        ex.executor.shutdown(wait=False)


def test_safe_executor_timeout_raises():
    ex = SafeExecutor(max_workers=1, default_timeout=0.01)
    try:
        with pytest.raises(Exception):
            ex.submit("slow", lambda: __import__("time").sleep(0.1))
    finally:
        ex.executor.shutdown(wait=False)
