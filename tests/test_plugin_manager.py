import pytest

from plugin_manager import PluginManager


class DummyPlugin:
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True


def test_plugin_manager_load_and_start():
    manager = PluginManager()

    plugin = DummyPlugin()

    manager.plugins = {"dummy": plugin}

    manager.start_plugins()

    assert plugin.started is True