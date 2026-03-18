from telegram_listener import SignalQueue


def test_queue_push_and_pop_order():
    q = SignalQueue(max_size=10)

    q.push({"id": 1})
    q.push({"id": 2})
    q.push({"id": 3})

    first = q.pop()
    second = q.pop()
    third = q.pop()

    assert first["id"] == 1
    assert second["id"] == 2
    assert third["id"] == 3


def test_queue_empty_pop_returns_none():
    q = SignalQueue(max_size=5)

    result = q.pop()

    assert result is None


def test_queue_respects_max_size():
    q = SignalQueue(max_size=2)

    q.push({"id": 1})
    q.push({"id": 2})
    q.push({"id": 3})

    # se la queue è piena deve rimanere max_size
    assert q.size() <= 2


def test_queue_size_tracking():
    q = SignalQueue(max_size=5)

    assert q.size() == 0

    q.push({"id": 1})
    q.push({"id": 2})

    assert q.size() == 2

    q.pop()

    assert q.size() == 1