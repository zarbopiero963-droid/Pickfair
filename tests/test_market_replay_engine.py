class MarketReplay:

    def __init__(self, ticks):
        self.ticks = ticks

    def replay(self):
        return list(self.ticks)


def test_replay_is_deterministic():

    ticks = [
        {"price": 2.0, "size": 10},
        {"price": 2.1, "size": 5},
        {"price": 2.2, "size": 8},
    ]

    replay = MarketReplay(ticks)

    first = replay.replay()
    second = replay.replay()

    assert first == second