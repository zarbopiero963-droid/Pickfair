import pytest

from telegram_sender import TelegramSender


def test_sender_init():
    sender = TelegramSender()

    assert sender is not None