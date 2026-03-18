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


def test_parse_master_signal_structure():
    msg = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11"
    )

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_id"] == "1.123"
    assert result["selection_id"] == 11
    assert result["side"] == "BACK"
    assert result["action"] == "BACK"
    assert float(result["price"]) == 2.10
    assert result["market_type"] == "MATCH_ODDS"


def test_parse_legacy_signal_format():
    msg = "Over 2.5 @2.10 Stake 10 Punta"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "OVER_UNDER"
    assert result["selection"] == "Over 2.5"
    assert result["side"] == "BACK"
    assert float(result["stake"]) == 10.0


def test_parse_invalid_message_returns_none():
    msg = "ciao questo non è un segnale valido"

    result = parse_signal_message(msg)

    assert result is None


def test_parse_cashout_all_message():
    msg = "CASHOUT ALL market_id=1.999"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"