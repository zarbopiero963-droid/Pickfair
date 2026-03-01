import concurrent.futures
import logging

logger = logging.getLogger("EXEC")

class SafeExecutor:
    def __init__(self, max_workers=4, default_timeout=30):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.default_timeout = default_timeout

    def submit(self, name, fn, *args, timeout=None, **kwargs):
        future = self.executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout or self.default_timeout)
        except concurrent.futures.TimeoutError:
            logger.error("[EXEC] Timeout in %s", name)
            future.cancel()
            raise