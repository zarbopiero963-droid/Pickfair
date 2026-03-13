from safe_mode import get_safe_mode_manager, reset_safe_mode


def test_safe_mode_report_error_increments_counter_and_records_error():
    reset_safe_mode()
    sm = get_safe_mode_manager()

    triggered = sm.report_error("test", "error", "1.1")
    info = sm.get_status_info()

    assert triggered is False
    assert info["status"] == "normal"
    assert info["consecutive_errors"] == 1
    assert len(info["recent_errors"]) >= 1
    assert info["recent_errors"][-1]["type"] == "test"