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
parse_signal_message = listener_mod.parse_signal_message


def test_parse_legacy_lay_signal_contract():
    msg = "Under 2.5 @3.10 Stake 7 Banca"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "OVER_UNDER"
    assert result["selection"] == "Under 2.5"
    assert result["side"] == "LAY"
    assert result["action"] == "LAY"
    assert float(result["price"]) == 3.10
    assert float(result["stake"]) == 7.0


def test_parse_signal_trims_spaces_and_newlines():
    msg = "\n   Over 2.5 @2.20 Stake 5 Punta   \n"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["selection"] == "Over 2.5"
    assert result["side"] == "BACK"
    assert float(result["price"]) == 2.20
    assert float(result["stake"]) == 5.0


def test_signal_queue_accepts_parsed_runtime_payload():
    queue = SignalQueue(maxsize=5)

    msg = "Over 2.5 @2.20 Stake 5 Punta"
    parsed = parse_signal_message(msg)

    assert parsed is not None

    queue.push(parsed)
    popped = queue.pop()

    assert popped["selection"] == "Over 2.5"
    assert popped["side"] == "BACK"
    assert float(popped["stake"]) == 5.0


def test_signal_queue_returns_none_when_empty():
    queue = SignalQueue(maxsize=2)

    assert queue.pop() is None
    assert len(queue) == 0