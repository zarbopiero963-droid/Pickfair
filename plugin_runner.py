import concurrent.futures
import logging
import time

logger = logging.getLogger("PLUGIN")

class PluginRunner:
    def __init__(self, timeout=2):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.timeout = timeout
        self.fail_counts = {}

    def run(self, plugin_name, fn, *args, **kwargs):
        future = self.executor.submit(fn, *args, **kwargs)

        try:
            return future.result(timeout=self.timeout)
        except Exception as e:
            self.fail_counts[plugin_name] = self.fail_counts.get(plugin_name, 0) + 1
            logger.error("[PLUGIN] %s failed (%s)", plugin_name, e)

            if self.fail_counts[plugin_name] >= 5:
                logger.error("[PLUGIN] %s auto-disabled", plugin_name)

            return None