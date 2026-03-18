from market_tracker import MarketTracker


def test_tracker_initialization():
    tracker = MarketTracker()

    assert tracker is not None


def test_add_market():
    tracker = MarketTracker()

    tracker.add_market({
        "marketId": "1.100",
        "name": "Match Odds"
    })

    markets = tracker.get_markets()

    assert len(markets) == 1
    assert markets[0]["marketId"] == "1.100"


def test_update_market():
    tracker = MarketTracker()

    tracker.add_market({
        "marketId": "1.200",
        "name": "Match Odds"
    })

    tracker.update_market("1.200", {
        "status": "OPEN"
    })

    market = tracker.get_market("1.200")

    assert market["status"] == "OPEN"


def test_remove_market():
    tracker = MarketTracker()

    tracker.add_market({
        "marketId": "1.300",
        "name": "Match Odds"
    })

    tracker.remove_market("1.300")

    markets = tracker.get_markets()

    assert len(markets) == 0