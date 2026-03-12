from safe_mode import get_safe_mode_manager


def test_safe_mode_toggle():
    sm = get_safe_mode_manager()

    sm.activate_safe_mode("test")

    assert sm.is_safe_mode_active

    sm.deactivate_safe_mode()

    assert not sm.is_safe_mode_active