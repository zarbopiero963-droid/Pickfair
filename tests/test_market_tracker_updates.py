from market_tracker import MarketTracker


def test_market_tracker_updates():
    tracker = MarketTracker()

    tracker.update_market("1.1", {"price": 2.0})

    assert "1.1" in tracker.markets