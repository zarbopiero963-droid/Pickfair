import importlib
import sys
import types

def _install_telethon_stub():
    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = object
    telethon.events = object()

    sessions = types.ModuleType("telethon.sessions")

    class DummyStringSession:
        def __init__(self, *args, **kwargs):
            pass

    sessions.StringSession = DummyStringSession

    sys.modules["telethon"] = telethon
    sys.modules["telethon.sessions"] = sessions

_install_telethon_stub()

listener = importlib.import_module("telegram_listener")
parse_signal_message = listener.parse_signal_message


def test_master_signal_full_contract():
    msg = """
    MASTER SIGNAL
    event_name: Juve - Milan
    market_name: Match Odds
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
    assert result["price"] == 2.10
    assert result["market_type"] == "MATCH_ODDS"


def test_master_signal_missing_fields_returns_none():
    msg = "MASTER SIGNAL\nselection: Juve"

    result = parse_signal_message(msg)

    assert result is None


def test_master_signal_case_insensitive():
    msg = """
    master signal
    EVENT_NAME: Juve - Milan
    MARKET_NAME: Match Odds
    SELECTION: Juve
    ACTION: BACK
    MASTER_PRICE: 2.10
    MARKET_ID: 1.123
    SELECTION_ID: 11
    """

    result = parse_signal_message(msg)

    assert result["selection_id"] == 11
    assert result["side"] == "BACK"