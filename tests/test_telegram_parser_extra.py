from telegram_listener import parse_signal_message


def test_parse_signal_message_exists():
    assert callable(parse_signal_message)


def test_parse_signal_message_empty():
    assert parse_signal_message("") is None
    assert parse_signal_message("   ") is None
    assert parse_signal_message(None) is None


def test_parse_signal_message_master_signal():
    msg = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11"
    )

    res = parse_signal_message(msg)

    assert res is not None
    assert res["market_id"] == "1.123"
    assert res["selection_id"] == 11
    assert res.get("side") == "BACK"


def test_parse_signal_message_legacy_signal():
    msg = "🎯 Juve - Milan\nOver 2.5\n@ 2.10\nStake 10\nPunta"

    res = parse_signal_message(msg)

    assert res is not None
    assert res.get("odds") == 2.10