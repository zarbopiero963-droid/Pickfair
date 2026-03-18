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


def test_cashout_all_signal_parses_runtime_contract():
    msg = "CASHOUT ALL market_id=1.999"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"
    assert result["market_id"] == "1.999"


def test_cashout_partial_signal_parses_market_and_selection():
    msg = "CASHOUT PARTIAL market_id=1.777 selection_id=12"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "PARTIAL"
    assert result["market_id"] == "1.777"
    assert result["selection_id"] == 12


def test_cashout_signal_is_case_insensitive():
    msg = "cashout all market_id=1.321"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"
    assert result["market_id"] == "1.321"


def test_cashout_invalid_without_market_id_returns_none():
    msg = "CASHOUT ALL"

    result = parse_signal_message(msg)

    assert result is None