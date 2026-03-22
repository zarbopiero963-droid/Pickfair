import logging
import threading

logger = logging.getLogger("SHUTDOWN")


class ShutdownManager:
    """
    FIX #35: coordinated, race-safe shutdown manager.

    - stop_event: threads can poll/wait on this to stop before resources close
    - duplicate registration prevention per name
    - shutdown() is idempotent: concurrent calls run the sequence only once
    - deterministic order preserved via priority sort
    """

    def __init__(self):
        self.handlers = []
        self._registered_names = set()
        self._lock = threading.Lock()
        # Threads can wait on this to know they should stop
        self.stop_event = threading.Event()
        self._shutdown_started = False

    def register(self, name, fn, priority=10):
        """Register a shutdown handler. Duplicate names are silently ignored."""
        with self._lock:
            if name in self._registered_names:
                logger.warning(
                    "[SHUTDOWN] Duplicate registration ignored: %s", name
                )
                return
            self._registered_names.add(name)
            self.handlers.append((priority, name, fn))
            self.handlers.sort(key=lambda x: x[0])

    def signal_stop(self):
        """
        Set stop_event so running threads know to drain and exit before
        resources (DB, executor, etc.) are closed by shutdown().
        """
        self.stop_event.set()

    def shutdown(self):
        """
        Execute registered handlers in priority order.
        Sets stop_event first so threads stop before resources are torn down.
        Idempotent: a second concurrent call returns immediately.
        """
        with self._lock:
            if self._shutdown_started:
                logger.warning(
                    "[SHUTDOWN] Already in progress, skipping duplicate call"
                )
                return
            self._shutdown_started = True
            handlers_snapshot = list(self.handlers)

        # Signal threads to stop BEFORE tearing down resources
        self.stop_event.set()

        for _, name, fn in handlers_snapshot:
            try:
                logger.info("[SHUTDOWN] %s", name)
                fn()
            except Exception as e:
                logger.exception("Shutdown error in %s: %s", name, e)

