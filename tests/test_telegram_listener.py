import pytest
from telegram_listener import TelegramListener

@pytest.fixture
def listener():
    return TelegramListener(api_id=1, api_hash="hash")

def test_parse_master_signal(listener):
    msg = (
        "🟢 MASTER SIGNAL\n\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 456"
    )
    res = listener.parse_signal(msg)
    assert res is not None
    assert res["market_id"] == "1.123"
    assert res["action"] == "BACK"
    assert res["price"] == 2.10
    assert res["match"] == "Juve - Milan"

def test_parse_master_signal_incomplete_and_malformed(listener):
    res = listener.parse_signal("🟢 MASTER SIGNAL\nevent_name: Juve - Milan")
    assert res is None

    msg2 = (
        "🟢 MASTER SIGNAL\n"
        "action: STRANA\n"
        "master_price: 2.10\n"
        "market_id: 1.1\n"
        "selection_id: 1"
    )
    res2 = listener.parse_signal(msg2)
    assert res2 is not None
    assert res2["action"] == "BACK"

def test_parse_legacy_signals(listener):
    res_back = listener.parse_signal(
        "🎯 Juve - Milan\nOver 2.5\n@ 2.10\nStake 10\nPunta"
    )
    assert res_back is not None
    assert res_back["action"] == "BACK"
    assert res_back["price"] == 2.10
    assert res_back["match"] == "Juve - Milan"
    assert res_back["selection"] == "Over 2.5"

    res_cashout = listener.parse_signal("CASHOUT TUTTO")
    assert res_cashout is not None
    assert res_cashout["action"] == "CASHOUT"
    assert res_cashout["market_type"] == "CASHOUT"

def test_custom_patterns_tolerances(listener):
    listener.custom_patterns = [
        {"pattern": "SEGRETO", "name": "Custom", "bet_side": "LAY"}
    ]
    res = listener.parse_signal("Messaggio SEGRETO @ 3.0")
    assert res is not None
    assert res["action"] == "LAY"
    assert res["price"] == 3.0
    assert res["source"] == "CUSTOM_PATTERN"

