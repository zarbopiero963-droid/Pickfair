from telegram_sender import TelegramSender


class DummyClient:
    def send_message(self, chat_id, text):
        return True


def test_sender_init():
    sender = TelegramSender(client=DummyClient())

    assert sender.client is not None


def test_sender_send_message():
    sender = TelegramSender(client=DummyClient())

    result = sender.send("123", "hello")

    assert result is True