import concurrent.futures
import logging

logger = logging.getLogger("EXEC")


class SafeExecutor:
    def __init__(self, max_workers: int = 4, default_timeout: int = 30):
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


class _ExecutorManagerFacade:
    """Runtime compatibility facade without expanding static public API surface."""

    def __init__(self, max_workers: int = 4, default_timeout: int = 30):
        self._safe_executor = SafeExecutor(
            max_workers=max_workers,
            default_timeout=default_timeout,
        )
        self.executor = self._safe_executor.executor
        self.running = True

    def submit(self, name, fn, *args, timeout=None, **kwargs):
        return self._safe_executor.submit(name, fn, *args, timeout=timeout, **kwargs)

    def shutdown(self, wait: bool = False):
        if self.running:
            self.executor.shutdown(wait=wait)
            self.running = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.shutdown(wait=False)
        return False


# Runtime alias for backward compatibility.
ExecutorManager = _ExecutorManagerFacade