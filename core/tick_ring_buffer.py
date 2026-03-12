from collections import deque


class TickRingBuffer:
    def __init__(self, maxlen: int = 10000):
        self._buf = deque(maxlen=maxlen)

    def push(self, item):
        self._buf.append(item)

    def pop(self):
        if self._buf:
            return self._buf.popleft()
        return None

    def drain(self, limit: int = 1000):
        items = []
        for _ in range(limit):
            if not self._buf:
                break
            items.append(self._buf.popleft())
        return items

    def __len__(self):
        return len(self._buf)