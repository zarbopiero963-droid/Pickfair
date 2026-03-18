from safe_mode_manager import SafeModeManager


def test_error_message_stored():

    manager = SafeModeManager()

    manager.trigger("api error")

    assert "api error" in manager.last_reason