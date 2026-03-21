import concurrent.futures
import logging

logger = logging.getLogger("PLUGIN")


class PluginRunner:
    FAIL_THRESHOLD = 5

    def __init__(self, timeout=2):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.timeout = timeout
        self.fail_counts = {}
        # FIX #31: disabled_plugins tracks actually-disabled plugins.
        # Old code logged "auto-disabled" but never prevented future execution.
        self.disabled_plugins = set()

    def is_disabled(self, plugin_name: str) -> bool:
        """Return True if this plugin has been auto-disabled."""
        return plugin_name in self.disabled_plugins

    def reset(self, plugin_name: str):
        """Reset failure count and re-enable a previously auto-disabled plugin."""
        self.fail_counts.pop(plugin_name, None)
        self.disabled_plugins.discard(plugin_name)

    def run(self, plugin_name, fn, *args, **kwargs):
        # FIX #31: skip execution if the plugin is disabled.
        if plugin_name in self.disabled_plugins:
            logger.warning("[PLUGIN] %s is auto-disabled, skipping", plugin_name)
            return None

        future = self.executor.submit(fn, *args, **kwargs)

        try:
            return future.result(timeout=self.timeout)
        except Exception as e:
            count = self.fail_counts.get(plugin_name, 0) + 1
            self.fail_counts[plugin_name] = count
            logger.error("[PLUGIN] %s failed (%s)", plugin_name, e)

            if count >= self.FAIL_THRESHOLD:
                # FIX #31: actually disable, not just log.
                self.disabled_plugins.add(plugin_name)
                logger.error(
                    "[PLUGIN] %s auto-disabled after %d failures",
                    plugin_name,
                    count,
                )

            return None

