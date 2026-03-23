import logging
import threading

logger = logging.getLogger("SHUTDOWN")


class ShutdownManager:
    """
    FIX #35: coordinated, race-safe shutdown manager.

    Changes from the previous version:
    - stop_event: threads can poll/wait on this to stop before resources close
    - register_worker(thread, timeout): registers worker threads that must be
      joined (drained) BEFORE any resource-closing handler runs.  This prevents
      a handler (e.g. DB close) from executing while a worker is still writing.
    - duplicate registration prevention per name
    - shutdown() is idempotent: concurrent calls run the sequence only once
    - deterministic order preserved via priority sort

    Shutdown sequence
    -----------------
    1. stop_event.set()           — signal all workers to drain and exit
    2. join each registered worker (with timeout)
    3. run registered handlers in priority order
    """

    def __init__(self):
        self.handlers = []
        self._registered_names = set()
        self._workers: list = []           # list of (thread, timeout_seconds)
        self._lock = threading.Lock()
        # Threads can wait on this to know they should stop
        self.stop_event = threading.Event()
        self._shutdown_started = False

    def register(self, name: str, fn, priority: int = 10):
        """Register a shutdown handler.  Duplicate names are silently ignored."""
        with self._lock:
            if name in self._registered_names:
                logger.warning(
                    "[SHUTDOWN] Duplicate registration ignored: %s", name
                )
                return
            self._registered_names.add(name)
            self.handlers.append((priority, name, fn))
            self.handlers.sort(key=lambda x: x[0])

    def register_worker(self, thread: threading.Thread, timeout: float = 5.0):
        """
        Register a worker thread to be joined after stop_event is set but
        BEFORE any resource-closing handlers run.

        Workers should observe stop_event and exit cleanly within *timeout*
        seconds.  If a worker does not exit in time it is logged as a warning
        but shutdown continues.
        """
        with self._lock:
            self._workers.append((thread, timeout))

    def signal_stop(self):
        """
        Set stop_event so running threads know to drain and exit before
        resources (DB, executor, etc.) are closed by shutdown().
        """
        self.stop_event.set()

    def shutdown(self):
        """
        Execute shutdown in a safe, ordered sequence:
          1. Set stop_event so workers begin draining.
          2. Join each registered worker (up to its timeout).
          3. Run registered handlers in priority order.

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
            workers_snapshot = list(self._workers)

        # ── Step 1: signal all threads to stop ───────────────────────────────
        self.stop_event.set()

        # ── Step 2: join workers so they drain before resources close ─────────
        for thread, timeout in workers_snapshot:
            if thread.is_alive():
                logger.info(
                    "[SHUTDOWN] Waiting for worker '%s' (timeout=%.1fs)…",
                    thread.name, timeout,
                )
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(
                        "[SHUTDOWN] Worker '%s' did not stop within %.1fs",
                        thread.name, timeout,
                    )

        # ── Step 3: run resource-closing handlers ─────────────────────────────
        for _, name, fn in handlers_snapshot:
            try:
                logger.info("[SHUTDOWN] %s", name)
                fn()
            except Exception as e:
                logger.exception("Shutdown error in %s: %s", name, e)
