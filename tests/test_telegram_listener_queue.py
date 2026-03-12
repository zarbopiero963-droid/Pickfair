from telegram_listener import SignalQueue, TelegramListener


def test_signal_queue_add_get_clear():
    q = SignalQueue(max_size=10)

    q.add({"a": 1})
    q.add({"b": 2})

    pending = q.get_pending()
    assert len(pending) == 2

    q.remove({"a": 1})
    assert len(q.get_pending()) == 1

    q.clear()
    assert q.get_pending() == []


def test_listener_parse_signal_legacy_back():
    listener = TelegramListener(api_id=1, api_hash="x")

    signal = listener.parse_signal("BACK @ 2.50")

    assert signal is not None
    assert signal["action"] == "BACK"