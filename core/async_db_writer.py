import threading
import time
from collections import deque


class AsyncDBWriter:
    """
    Non-blocking DB writer.

    Ensures trading engine never blocks on DB I/O.
    """

    def __init__(self, db, maxlen: int = 5000, sleep_idle: float = 0.001):

        self.db = db
        self.queue = deque(maxlen=maxlen)

        self.running = False
        self.thread = None

        self.sleep_idle = sleep_idle

    def start(self):

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="AsyncDBWriter",
        )

        self.thread.start()

    def stop(self):

        self.running = False

        if self.thread:
            self.thread.join(timeout=2)

    def submit(self, kind: str, payload: dict):

        self.queue.append((kind, payload))

    def _loop(self):

        while self.running:

            if not self.queue:
                time.sleep(self.sleep_idle)
                continue

            kind, payload = self.queue.popleft()

            try:

                if kind == "bet":
                    self.db.save_bet(**payload)

                elif kind == "cashout":
                    self.db.save_cashout_transaction(**payload)

                elif kind == "simulation_bet":
                    self.db.save_simulation_bet(**payload)

            except Exception:
                pass