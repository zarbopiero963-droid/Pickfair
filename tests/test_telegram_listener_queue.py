import importlib
import sys
import types


def _install_telethon_stub():
    telethon_mod = types.ModuleType("telethon")
    telethon_mod.TelegramClient = object
    telethon_mod.events = object()

    sessions_mod = types.ModuleType("telethon.sessions")

    class DummyStringSession:
        def __init__(self, *args, **kwargs):
            pass

    sessions_mod.StringSession = DummyStringSession

    sys.modules["telethon"] = telethon_mod
    sys.modules["telethon.sessions"] = sessions_mod


_install_telethon_stub()

listener_mod = importlib.import_module("telegram_listener")
SignalQueue = listener_mod.SignalQueue


def test_signal_queue_fifo_order():
    queue = SignalQueue(maxsize=10)

    queue.push({"id": 1})
    queue.push({"id": 2})
    queue.push({"id": 3})

    assert queue.pop()["id"] == 1
    assert queue.pop()["id"] == 2
    assert queue.pop()["id"] == 3


def test_signal_queue_empty_pop_returns_none():
    queue = SignalQueue(maxsize=5)

    result = queue.pop()

    assert result is None


def test_signal_queue_overflow_discards_oldest():
    queue = SignalQueue(maxsize=2)

    queue.push({"id": 1})
    queue.push({"id": 2})
    queue.push({"id": 3})

    first = queue.pop()
    second = queue.pop()

    assert first["id"] == 2
    assert second["id"] == 3


def test_signal_queue_length_tracking():
    queue = SignalQueue(maxsize=5)

    queue.push({"id": 1})
    queue.push({"id": 2})

    assert len(queue) == 2

    queue.pop()

    assert len(queue) == 1