"""
EventBus (Pub/Sub) — core runtime module
Il sistema nervoso centrale dell'applicazione.
Permette ai moduli di comunicare senza conoscersi (Decoupling totale).

FIX #37 (applied to THIS module — the one used at runtime):
Previously the async implementation was only in the root event_bus.py,
while this module (core/event_bus.py) still used the old synchronous
publish() which blocked the publisher for the duration of every subscriber.

Changes from the old synchronous implementation:
  - Each subscriber is dispatched to a ThreadPoolExecutor (max_workers=4)
    so slow subscribers cannot block the publisher or each other.
  - Exceptions in subscribers are logged via Future done-callbacks and are
    never silently lost.
  - subscribe / unsubscribe / publish API is unchanged — fully backward-compatible.
  - Added shutdown(wait) to allow clean teardown on application exit.
"""

__all__ = ["EventBus"]

import concurrent.futures
import logging
import threading

logger = logging.getLogger(__name__)


class EventBus:
    """
    Thread-safe, non-blocking Pub/Sub event bus.

    publish() submits each subscriber callback to a ThreadPoolExecutor and
    returns immediately, regardless of how long individual subscribers take.
    """

    def __init__(self, max_workers: int = 4):
        self._subscribers: dict = {}
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
        immediately after submitting all tasks.  Subscriber exceptions are
        caught and logged by the done-callback so they are never silently lost.
        """
        with self._lock:
            # Copy under lock to avoid races with subscribe/unsubscribe
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
        """Shut down the internal thread pool.  Call on application exit."""
        self._executor.shutdown(wait=wait)
