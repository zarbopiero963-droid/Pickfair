from collections import deque


class FastWoMState:
    def __init__(self, max_ticks: int = 128):
        self.ticks = deque(maxlen=max_ticks)
        self.sum_back = 0.0
        self.sum_lay = 0.0

    def push(self, tick):
        if len(self.ticks) == self.ticks.maxlen:
            old = self.ticks[0]
            self.sum_back -= old["back_volume"]
            self.sum_lay -= old["lay_volume"]

        self.ticks.append(tick)
        self.sum_back += tick["back_volume"]
        self.sum_lay += tick["lay_volume"]

    def wom(self) -> float:
        total = self.sum_back + self.sum_lay
        if total <= 0:
            return 0.5
        return self.sum_back / total