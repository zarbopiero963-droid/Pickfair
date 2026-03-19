
from plugin_runner import PluginRunner


class DummyPlugin:
    def run(self):
        return "ok"


def test_plugin_runner_executes_plugin():
    runner = PluginRunner()

    plugin = DummyPlugin()

    result = runner.run_plugin(plugin)

    assert result == "ok"