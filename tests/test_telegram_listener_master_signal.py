from telegram_listener import parse_signal_message


def test_parse_back_signal():
    msg = "BACK @2.5 selection_id=101 market_id=1.123456"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["action"] == "BACK"
    assert result["selection_id"] == 101
    assert result["market_id"] == "1.123456"
    assert result["price"] == 2.5


def test_parse_lay_signal():
    msg = "LAY @3.1 selection_id=200 market_id=1.999999"

    result = parse_signal_message(msg)

    assert result["action"] == "LAY"
    assert result["selection_id"] == 200
    assert result["price"] == 3.1


def test_parse_invalid_signal_returns_none():
    msg = "random message with no trading info"

    result = parse_signal_message(msg)

    assert result is None