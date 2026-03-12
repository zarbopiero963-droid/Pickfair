import pytest

from telegram_listener import parse_signal_message


def test_master_signal_parse():
    msg = "BACK @2.0 selection_id=123 market_id=1.123456"

    result = parse_signal_message(msg)

    assert result["action"] == "BACK"