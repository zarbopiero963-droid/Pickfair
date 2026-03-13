from auto_updater import AutoUpdater


def test_auto_updater_initial_state():
    updater = AutoUpdater()

    assert updater.enabled is False
    assert updater.current_version is None


def test_auto_updater_enable_disable():
    updater = AutoUpdater()

    updater.enable()
    assert updater.enabled is True

    updater.disable()
    assert updater.enabled is False