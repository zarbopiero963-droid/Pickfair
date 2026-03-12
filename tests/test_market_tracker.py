import time

from market_tracker import MarketCache, DeltaDetector


def test_market_cache_hit_miss_and_invalidate():
    cache = MarketCache(ttl=1.0, max_size=2)
    assert cache.get("1.1") is None

    cache.set("1.1", {"marketId": "1.1", "x": 1})
    value = cache.get("1.1")
    assert value == {"marketId": "1.1", "x": 1}
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1

    cache.invalidate("1.1")
    assert cache.get("1.1") is None


def test_market_cache_expires_entries(monkeypatch):
    cache = MarketCache(ttl=0.01, max_size=2)
    cache.set("1.1", {"x": 1})
    import market_tracker as mt
    original_time = mt.time.time
    monkeypatch.setattr(mt.time, "time", lambda: original_time() + 100)
    assert cache.get("1.1") is None


def test_delta_detector_detects_first_read_then_skips_small_changes():
    delta = DeltaDetector(min_price_change=0.05, min_volume_change=10)

    changed, reason = delta.has_changed("1.1", 1, 2.0, 2.02, 50, 50)
    assert changed is True
    assert "Prima lettura" in reason

    changed, _ = delta.has_changed("1.1", 1, 2.01, 2.03, 52, 52)
    assert changed is False

    changed, reason = delta.has_changed("1.1", 1, 2.2, 2.22, 52, 52)
    assert changed is True
    assert "Prezzo" in reason or "Volume" in reason
