from telegram_controller import TelegramController


class DummySender:

    def __init__(self):
        self.sent = []

    def send_message_sync(self, chat_id, text):
        self.sent.append((chat_id, text))
        return True


def test_controller_sends_message():
    sender = DummySender()
    controller = TelegramController(sender)

    controller.notify("123", "hello")

    assert sender.sent == [("123", "hello")]


def test_controller_handles_empty_message():
    sender = DummySender()
    controller = TelegramController(sender)

    controller.notify("123", "")

    assert sender.sent == []