from telegram_listener import SignalQueue


def test_queue_push_pop_order():
    q = SignalQueue(maxsize=5)

    q.push({"id": 1})
    q.push({"id": 2})
    q.push({"id": 3})

    assert q.pop()["id"] == 1
    assert q.pop()["id"] == 2
    assert q.pop()["id"] == 3


def test_queue_overflow_discards_oldest():
    q = SignalQueue(maxsize=2)

    q.push({"id": 1})
    q.push({"id": 2})
    q.push({"id": 3})

    assert q.pop()["id"] == 2
    assert q.pop()["id"] == 3


def test_queue_len_tracking():
    q = SignalQueue(maxsize=3)

    q.push({"a": 1})
    q.push({"a": 2})

    assert len(q) == 2

    q.pop()

    assert len(q) == 1