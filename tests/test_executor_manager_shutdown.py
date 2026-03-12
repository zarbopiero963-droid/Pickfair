from executor_manager import ExecutorManager


def test_executor_shutdown():
    ex = ExecutorManager()

    ex.shutdown()

    assert ex.running is False or ex.running == False