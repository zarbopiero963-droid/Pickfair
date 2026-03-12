from telegram_listener import parse_signal_message


def test_invalid_signal_returns_none():
    result = parse_signal_message("random nonsense")

    assert result is None