from telegram_listener import TelegramListener


def _make_listener():
    return TelegramListener(api_id=12345, api_hash="hash")


def test_telegram_listener_parse_master_signal():
    listener = _make_listener()

    msg = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11\n"
    )

    result = listener.parse_signal(msg)

    assert result is not None
    assert result["market_id"] == "1.123"
    assert result["selection_id"] == 11
    assert result["side"] == "BACK"
    assert result["source"] == "MASTER_SIGNAL"


def test_telegram_listener_parse_legacy_signal():
    listener = _make_listener()

    msg = (
        "🆚 Juve - Milan\n"
        "Over 2.5\n"
        "@ 2.10\n"
        "stake 10\n"
        "punta"
    )

    result = listener.parse_signal(msg)

    assert result is not None
    assert result["side"] == "BACK"
    assert result["market_type"] == "OVER_UNDER"
    assert result["selection"] == "Over 2.5"
    assert result["odds"] == 2.10
    assert result["stake"] == 10.0