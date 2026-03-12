import pytest

from auto_updater import AutoUpdater


def test_auto_updater_init():
    updater = AutoUpdater()

    assert updater is not None