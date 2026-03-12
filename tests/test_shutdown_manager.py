from shutdown_manager import ShutdownManager


def test_shutdown_manager_executes_handlers_in_priority_order():
    mgr = ShutdownManager()
    executed = []

    mgr.register("late", lambda: executed.append("late"), priority=20)
    mgr.register("early", lambda: executed.append("early"), priority=5)
    mgr.shutdown()

    assert executed == ["early", "late"]


def test_shutdown_manager_continues_after_handler_error():
    mgr = ShutdownManager()
    executed = []

    def bad():
        executed.append("bad")
        raise RuntimeError("boom")

    def good():
        executed.append("good")

    mgr.register("bad", bad, priority=1)
    mgr.register("good", good, priority=2)
    mgr.shutdown()

    assert executed == ["bad", "good"]
