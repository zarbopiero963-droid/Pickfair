import logging

logger = logging.getLogger("SHUTDOWN")


class ShutdownManager:
    def __init__(self):
        self.handlers = []
        self.is_shutdown = False

    def register(self, name_or_fn=None, fn=None, priority=10):
        # Support both register(name, fn) and register(fn)
        if fn is None and callable(name_or_fn):
            fn = name_or_fn
            name_or_fn = f"handler_{len(self.handlers)}"
        self.handlers.append((priority, name_or_fn or "", fn))
        self.handlers.sort(key=lambda x: x[0])

    def shutdown(self):
        for _, name, fn in self.handlers:
            try:
                logger.info("[SHUTDOWN] %s", name)
                fn()
            except Exception as e:
                logger.exception("Shutdown error: %s", e)
        self.is_shutdown = True

