from executor_manager import ExecutorManager


def test_executor_manager_parallel_smoke():
    """
    Basic smoke test to ensure ExecutorManager can be created
    and exposes the expected shutdown interface.
    """
    ex = ExecutorManager()

    assert ex is not None
    assert hasattr(ex, "shutdown")
    assert hasattr(ex, "running")


def test_executor_manager_parallel_shutdown():
    """
    Ensure shutdown works correctly even when called directly.
    """
    ex = ExecutorManager()

    ex.shutdown()

    assert ex.running is False or ex.running == False