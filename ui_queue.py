import time
import queue
import threading
import logging

logger = logging.getLogger("UIQ")

class UIQueue:
    def __init__(self, root, fps=30, max_per_tick=50):
        self.root = root
        self.queue = queue.Queue()
        self.interval = int(1000 / fps)
        self.max_per_tick = max_per_tick

        self._executed = 0
        self._dropped = 0
        self._errors = 0
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self.root.after(self.interval, self._process)
        logger.info("[UIQ] Started")

    def stop(self):
        self._running = False

    def post(self, fn, *args, **kwargs):
        try:
            self.queue.put_nowait((fn, args, kwargs))
        except queue.Full:
            self._dropped += 1

    def _process(self):
        if not self._running:
            return

        count = 0
        start = time.time()

        while count < self.max_per_tick:
            try:
                fn, args, kwargs = self.queue.get_nowait()
            except queue.Empty:
                break

            try:
                fn(*args, **kwargs)
                self._executed += 1
            except Exception as e:
                self._errors += 1
                logger.exception("[UIQ] Error executing task: %s", e)

            count += 1

        if time.time() - start > 0.05:
            logger.warning("[UIQ] Slow tick detected")

        self.root.after(self.interval, self._process)

    def stats(self):
        return {
            "executed": self._executed,
            "dropped": self._dropped,
            "errors": self._errors,
            "qsize": self.queue.qsize()
        }