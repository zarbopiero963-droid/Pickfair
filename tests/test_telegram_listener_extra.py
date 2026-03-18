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
TelegramListener = listener_mod.TelegramListener
parse_signal_message = listener_mod.parse_signal_message


def test_parse_master_signal_with_extra_noise_lines_still_extracts_core_fields():
    msg = """
    🟢 MASTER SIGNAL

    something irrelevant: ignore me
    event_name: Juve - Milan
    market_name: Match Odds
    note: random note
    selection: Juve
    action: BACK
    master_price: 2.10
    market_id: 1.123
    selection_id: 11
    """

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_id"] == "1.123"
    assert result["selection_id"] == 11
    assert result["side"] == "BACK"
    assert float(result["price"]) == 2.10


def test_parse_legacy_signal_accepts_compact_at_syntax():
    msg = "Over 2.5@2.25 Stake 6 Punta"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["selection"] == "Over 2.5"
    assert result["side"] == "BACK"
    assert float(result["price"]) == 2.25
    assert float(result["stake"]) == 6.0


def test_parse_legacy_signal_accepts_lowercase_words():
    msg = "under 2.5 @3.10 stake 7 banca"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["side"] == "LAY"
    assert result["action"] == "LAY"
    assert float(result["price"]) == 3.10
    assert float(result["stake"]) == 7.0


def test_listener_parse_signal_method_matches_module_level_parser():
    listener = TelegramListener(api_id=0, api_hash="")

    msg = "Over 2.5 @2.20 Stake 5 Punta"

    a = parse_signal_message(msg)
    b = listener.parse_signal(msg)

    assert a == b


def test_signal_queue_overflow_keeps_latest_messages_only():
    queue = SignalQueue(maxsize=3)

    queue.push({"id": 1})
    queue.push({"id": 2})
    queue.push({"id": 3})
    queue.push({"id": 4})

    assert len(queue) == 3
    assert queue.pop()["id"] == 2
    assert queue.pop()["id"] == 3
    assert queue.pop()["id"] == 4