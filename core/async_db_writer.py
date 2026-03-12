import threading
from collections import deque


class AsyncDBWriter:
    def __init__(self, db, maxlen: int = 5000):
        self.db = db
        self.queue = deque(maxlen=maxlen)
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
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
                continue
            kind, payload = self.queue.popleft()
            try:
                if kind == "bet":
                    self.db.save_bet(**payload)
                elif kind == "cashout":
                    self.db.save_cashout_transaction(**payload)
            except Exception:
                pass