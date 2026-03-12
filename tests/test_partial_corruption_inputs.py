import pytest

from telegram_listener import parse_signal_message


def test_corrupted_message():
    msg = "%%%% invalid signal ####"

    result = parse_signal_message(msg)

    assert result is None or isinstance(result, dict)