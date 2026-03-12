import pytest

from telegram_listener import parse_signal_message


def test_cashout_parse():
    msg = "CASHOUT ALL market_id=1.123456"

    result = parse_signal_message(msg)

    assert result["action"] == "CASHOUT"