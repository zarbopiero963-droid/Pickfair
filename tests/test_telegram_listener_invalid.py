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
parse_signal_message = listener_mod.parse_signal_message


def test_invalid_empty_messages_return_none():
    assert parse_signal_message("") is None
    assert parse_signal_message("   ") is None
    assert parse_signal_message(None) is None


def test_invalid_garbage_text_returns_none():
    msg = "ciao questo messaggio non contiene alcun segnale di betting"

    result = parse_signal_message(msg)

    assert result is None


def test_invalid_master_signal_missing_market_id_returns_none():
    msg = """
    MASTER SIGNAL
    event_name: Juve - Milan
    market_name: Match Odds
    selection: Juve
    action: BACK
    master_price: 2.10
    selection_id: 11
    """

    result = parse_signal_message(msg)

    assert result is None


def test_invalid_master_signal_missing_selection_id_returns_none():
    msg = """
    MASTER SIGNAL
    event_name: Juve - Milan
    market_name: Match Odds
    selection: Juve
    action: BACK
    master_price: 2.10
    market_id: 1.123
    """

    result = parse_signal_message(msg)

    assert result is None


def test_invalid_legacy_signal_without_price_returns_none():
    msg = "Over 2.5 Stake 10 Punta"

    result = parse_signal_message(msg)

    assert result is None


def test_invalid_cashout_without_market_id_returns_none():
    msg = "CASHOUT ALL"

    result = parse_signal_message(msg)

    assert result is None