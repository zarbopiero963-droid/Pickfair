import asyncio

from telegram_sender import AdaptiveRateLimiter, TelegramSender


class DummyMsg:
    def __init__(self, msg_id=123):
        self.id = msg_id


class DummyClient:
    async def get_entity(self, chat_id):
        return chat_id

    async def send_message(self, entity, text):
        return DummyMsg(321)


class DummyDB:
    def __init__(self):
        self.logs = []

    def save_telegram_outbox_log(self, **kwargs):
        self.logs.append(kwargs)


def test_rate_limiter_success_and_failure_stats():
    rl = AdaptiveRateLimiter(base_delay=0.5)
    rl.record_success()
    rl.record_failure()
    stats = rl.get_stats()
    assert "current_delay" in stats
    assert "consecutive_successes" in stats


def test_telegram_sender_send_message_sync_success():
    sender = TelegramSender(client=DummyClient(), db=DummyDB(), default_chat_id="123")
    result = sender.send_message_sync("123", "hello", message_type="TEST")
    assert result.success is True
    assert result.message_id == 321


def test_telegram_sender_queue_default_message_uses_default_chat_id():
    sender = TelegramSender(client=DummyClient(), db=DummyDB(), default_chat_id="555")
    sender.queue_default_message("msg", message_type="PING")
    queued = sender._queue.get_nowait()
    assert queued.chat_id == "555"
    assert queued.text == "msg"
