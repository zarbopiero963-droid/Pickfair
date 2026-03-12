from collections import deque


class FastWoMState:
    """
    Ultra-fast rolling WoM (Weight of Money) calculator.

    Designed for hot-path analytics with minimal allocations.
    """

    def __init__(self, max_ticks: int = 128):
        self.ticks = deque(maxlen=max_ticks)
        self.sum_back = 0.0
        self.sum_lay = 0.0

    def push(self, tick: dict):
        """
        Add tick with fields:
        {
            "back_volume": float,
            "lay_volume": float
        }
        """

        if len(self.ticks) == self.ticks.maxlen:
            old = self.ticks[0]
            self.sum_back -= old["back_volume"]
            self.sum_lay -= old["lay_volume"]

        self.ticks.append(tick)

        self.sum_back += tick["back_volume"]
        self.sum_lay += tick["lay_volume"]

    def wom(self) -> float:
        """
        Returns Weight of Money ratio.
        """

        total = self.sum_back + self.sum_lay
        if total <= 0:
            return 0.5

        return self.sum_back / total

    def imbalance(self) -> float:
        """
        Returns imbalance metric.
        """

        total = self.sum_back + self.sum_lay
        if total <= 0:
            return 0.0

        return (self.sum_back - self.sum_lay) / total

    def snapshot(self) -> dict:
        return {
            "ticks": len(self.ticks),
            "sum_back": self.sum_back,
            "sum_lay": self.sum_lay,
            "wom": self.wom(),
        }