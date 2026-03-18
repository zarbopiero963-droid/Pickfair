from pnl_engine import PnLEngine


def test_duplicate_fills_filtered():

    pnl = PnLEngine()

    fills = [
        {"id": "A", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5},
        {"id": "A", "side": "BACK", "sizeMatched": 5, "averagePriceMatched": 2.5},
    ]

    seen = set()
    total = 0

    for f in fills:

        if f["id"] not in seen:
            seen.add(f["id"])
            total += pnl.calculate_back_pnl(f, best_lay_price=2.4)

    assert len(seen) == 1