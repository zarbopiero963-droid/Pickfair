import time

from executor_manager import ExecutorManager


def test_executor_runs_tasks_in_parallel():
    manager = ExecutorManager(max_workers=4, default_timeout=2)

    def slow(x):
        time.sleep(0.1)
        return x * 2

    start = time.time()

    futures = [
        manager.executor.submit(slow, i)
        for i in range(4)
    ]

    results = [f.result() for f in futures]

    elapsed = time.time() - start

    assert results == [0, 2, 4, 6]

    # parallel execution should take less than serial (0.4s)
    assert elapsed < 0.35

    manager.shutdown(wait=False)


def test_executor_submit_returns_result():
    manager = ExecutorManager(max_workers=2, default_timeout=1)

    result = manager.submit("sum", lambda a, b: a + b, 2, 5)

    assert result == 7

    manager.shutdown(wait=False)


def test_executor_shutdown_prevents_new_tasks():
    manager = ExecutorManager(max_workers=1, default_timeout=1)

    manager.shutdown(wait=False)

    try:
        manager.submit("x", lambda: 1)
        allowed = True
    except RuntimeError:
        allowed = False

    assert allowed is False