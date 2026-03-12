from shutdown_manager import ShutdownManager


def test_shutdown_manager_basic():
    sm = ShutdownManager()

    sm.register(lambda: None)

    sm.shutdown()

    assert sm.is_shutdown is True