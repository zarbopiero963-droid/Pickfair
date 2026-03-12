from shutdown_manager import ShutdownManager


def test_multiple_hooks():
    sm = ShutdownManager()

    called = []

    sm.register(lambda: called.append(1))
    sm.register(lambda: called.append(2))

    sm.shutdown()

    assert len(called) == 2