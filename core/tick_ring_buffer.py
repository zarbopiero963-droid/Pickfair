from collections import deque
from typing import Any


class TickRingBuffer:
    """
    Ultra-fast ring buffer for tick dispatch.
    Uses deque for O(1) append / popleft operations.
    """

    def __init__(self, maxlen: int = 10000):
        self._buf = deque(maxlen=maxlen)

    def push(self, item: Any) -> None:
        self._buf.append(item)

    def pop(self) -> Any:
        if self._buf:
            return self._buf.popleft()
        return None

    def drain(self, limit: int = 1000) -> list[Any]:
        items = []
        for _ in range(limit):
            if not self._buf:
                break
            items.append(self._buf.popleft())
        return items

    def peek(self) -> Any:
        if self._buf:
            return self._buf[0]
        return None

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

    def __bool__(self) -> bool:
        return bool(self._buf)