import pytest

from telegram_sender import TelegramSender


def test_format_message():
    sender = TelegramSender()

    msg = sender.format_message("test")

    assert "test" in msg