from safe_mode_manager import SafeModeManager


def test_safe_mode_activation():

    manager = SafeModeManager()

    manager.trigger("network failure")

    assert manager.is_active()