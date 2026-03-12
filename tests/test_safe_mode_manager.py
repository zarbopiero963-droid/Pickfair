from safe_mode import get_safe_mode_manager


def test_safe_mode_triggers_after_threshold():
    manager = get_safe_mode_manager()
    manager.reset()

    triggered_1 = manager.report_error("TestError", "first")
    triggered_2 = manager.report_error("TestError", "second")

    assert triggered_1 is False
    assert triggered_2 is True
    assert manager.is_safe_mode_active is True


def test_safe_mode_success_resets_consecutive_errors():
    manager = get_safe_mode_manager()
    manager.reset()

    manager.report_error("TestError", "first")
    assert manager.consecutive_errors >= 1

    manager.report_success()

    assert manager.consecutive_errors == 0


def test_safe_mode_status_info_shape():
    manager = get_safe_mode_manager()
    info = manager.get_status_info()

    assert "status" in info
    assert "consecutive_errors" in info
    assert "threshold" in info
    assert "recent_errors" in info