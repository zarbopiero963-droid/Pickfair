import asyncio

from telegram_sender import TelegramSender


class DummyMessage:
    def __init__(self, msg_id):
        self.id = msg_id


class DummyClient:
    def __init__(self):
        self.calls = 0

    async def get_entity(self, chat_id):
        return chat_id

    async def send_message(self, entity, text):
        self.calls += 1
        return DummyMessage(123)


def test_sender_successful_send():
    client = DummyClient()
    sender = TelegramSender(client=client)

    result = sender.send_message_sync("1", "hello")

    assert result.success is True
    assert result.message_id == 123
    assert result.error is None
    assert client.calls == 1


def test_sender_multiple_messages():
    client = DummyClient()
    sender = TelegramSender(client=client)

    sender.send_message_sync("1", "a")
    sender.send_message_sync("1", "b")

    assert client.calls == 2


def test_sender_handles_exception():
    class FailingClient(DummyClient):
        async def send_message(self, entity, text):
            raise RuntimeError("network failure")

    client = FailingClient()
    sender = TelegramSender(client=client, base_delay=0)

    result = sender.send_message_sync("1", "hello", max_retries=1)

    assert result.success is False
    assert "network failure" in result.error