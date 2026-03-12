from safe_mode import get_safe_mode_manager


def test_safe_mode_report_error():
    sm = get_safe_mode_manager()

    sm.report_error("test", "error", "1.1")

    assert True