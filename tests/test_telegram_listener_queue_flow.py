from telegram_listener import TelegramListener


def test_queue_enqueue():
    tl = TelegramListener()

    tl.enqueue_message("BACK @2.0 selection_id=1 market_id=1.123456")

    assert tl.queue.qsize() == 1