from telegram_sender import TelegramSender


class DummyMessage:
    def __init__(self, msg_id):
        self.id = msg_id


class RetryClient:
    def __init__(self):
        self.entity_calls = 0
        self.send_calls = 0

    async def get_entity(self, chat_id):
        self.entity_calls += 1
        return chat_id

    async def send_message(self, entity, text):
        self.send_calls += 1
        if self.send_calls == 1:
            raise TimeoutError("temporary timeout")
        return DummyMessage(777)


class AlwaysFailClient:
    def __init__(self):
        self.entity_calls = 0
        self.send_calls = 0

    async def get_entity(self, chat_id):
        self.entity_calls += 1
        return chat_id

    async def send_message(self, entity, text):
        self.send_calls += 1
        raise ConnectionError("network down")


def test_sender_retry_succeeds_after_temporary_failure():
    client = RetryClient()
    sender = TelegramSender(client=client, base_delay=0.0)

    result = sender.send_message_sync("123", "hello", max_retries=3)

    assert result.success is True
    assert result.message_id == 777
    assert result.error is None
    assert client.entity_calls == 2
    assert client.send_calls == 2
    assert sender._messages_sent == 1
    assert sender._messages_failed == 0


def test_sender_failure_after_exhausting_retries():
    client = AlwaysFailClient()
    sender = TelegramSender(client=client, base_delay=0.0)

    result = sender.send_message_sync("123", "hello", max_retries=2)

    assert result.success is False
    assert result.message_id is None
    assert "network down" in result.error
    assert client.entity_calls == 2
    assert client.send_calls == 2
    assert sender._messages_sent == 0
    assert sender._messages_failed == 1