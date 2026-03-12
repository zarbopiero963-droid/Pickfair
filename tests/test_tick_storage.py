from tick_storage import TickStorage


def test_tick_storage_push_and_get_last_tick():
    storage = TickStorage(max_ticks=5)
    storage.push_tick(11, 2.0, 1.99, 2.02, 100, 90, 50)

    last = storage.get_last_tick(11)
    assert last["ltp"] == 2.0
    assert last["back"] == 1.99
    assert last["lay"] == 2.02


def test_tick_storage_ltp_history_and_spread_history():
    storage = TickStorage(max_ticks=5)
    storage.push_tick(11, 2.0, 1.99, 2.02)
    storage.push_tick(11, 2.1, 2.08, 2.12)

    assert storage.get_ltp_history(11, limit=10) == [2.0, 2.1]
    spreads = storage.get_spread_history(11, limit=10)
    assert len(spreads) == 2
    assert spreads[0] > 0


def test_tick_storage_aggregate_ohlc_returns_candles():
    storage = TickStorage(max_ticks=10)
    storage.push_tick(11, 2.0, 1.99, 2.02, traded_volume=10)
    storage.push_tick(11, 2.2, 2.18, 2.24, traded_volume=20)

    candles = storage.aggregate_ohlc(11, interval_sec=9999)
    assert len(candles) == 1
    candle = candles[0]
    assert candle.open == 2.0
    assert candle.close == 2.2
    assert candle.high >= candle.low
