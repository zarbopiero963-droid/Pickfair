"""
EventBus (Pub/Sub)
Il sistema nervoso centrale dell'applicazione.
Permette ai moduli di comunicare senza conoscersi (Decoupling totale).
"""

__all__ = ["EventBus"]

import concurrent.futures
import logging
import threading

logger = logging.getLogger(__name__)


class EventBus:
    """
    FIX #37: subscriber execution is now asynchronous.

    Old: each subscriber was called synchronously in the publisher's thread.
    A slow subscriber blocked all subsequent subscribers AND the publisher
    itself. A failed subscriber silently swallowed the exception and moved on.

    New:
    - each subscriber is dispatched to a ThreadPoolExecutor (max_workers=4)
      so slow subscribers cannot block the publisher or each other
    - exceptions in subscribers are logged with their Future result
    - subscribe/unsubscribe API is unchanged
    - publish() returns immediately after dispatching all callbacks
    """

    def __init__(self, max_workers: int = 4):
        self._subscribers = {}
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="EventBus",
        )

    def subscribe(self, event_type: str, callback: callable):
        """Iscrive una funzione a un determinato tipo di evento."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: callable):
        """Rimuove l'iscrizione di una funzione a un evento."""
        with self._lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, data=None):
        """
        Pubblica un evento in modo non-bloccante.

        Each subscriber is dispatched to the thread pool; publish() returns
        immediately after submitting all tasks. Subscriber exceptions are
        caught and logged by the done-callback so they are never silently lost.
        """
        with self._lock:
            callbacks = self._subscribers.get(event_type, []).copy()

        for callback in callbacks:
            cb_name = getattr(callback, "__name__", repr(callback))
            future = self._executor.submit(callback, data)

            def _on_done(f, name=cb_name, etype=event_type):
                exc = f.exception()
                if exc is not None:
                    logger.error(
                        "[EventBus] Subscriber '%s' for '%s' raised: %s",
                        name, etype, exc,
                    )

            future.add_done_callback(_on_done)

    def shutdown(self, wait: bool = True):
        """Shut down the internal thread pool. Call on application exit."""
        self._executor.shutdown(wait=wait)