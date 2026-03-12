import time

from ai.wom_engine import WoMEngine


def test_wom_no_ticks_returns_none():
    engine = WoMEngine()
    assert engine.calculate_wom(101) is None


def test_wom_insufficient_ticks_returns_none():
    engine = WoMEngine()

    engine.record_tick(101, 2.0, 100, 2.02, 90)
    result = engine.calculate_wom(101)

    assert result is None


def test_wom_strong_back_signal():
    engine = WoMEngine()

    for _ in range(6):
        engine.record_tick(101, 2.0, 600, 2.02, 100)
        time.sleep(0.01)

    result = engine.calculate_enhanced_wom(101)

    assert result is not None
    assert result.wom > 0.55
    assert result.suggested_side == "BACK"


def test_wom_strong_lay_signal():
    engine = WoMEngine()

    for _ in range(6):
        engine.record_tick(101, 2.0, 80, 2.02, 700)
        time.sleep(0.01)

    result = engine.calculate_enhanced_wom(101)

    assert result is not None
    assert result.wom < 0.45
    assert result.suggested_side == "LAY"


def test_wom_momentum_clamped():
    engine = WoMEngine()

    for _ in range(10):
        engine.record_tick(101, 2.0, 800, 2.02, 100)

    momentum = engine.calculate_momentum(101)

    assert -1.0 <= momentum <= 1.0