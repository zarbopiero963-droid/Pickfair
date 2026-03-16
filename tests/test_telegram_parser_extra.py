import importlib
import sys
import types


def _load_parser_module():
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

    if "telegram_listener" in sys.modules:
        del sys.modules["telegram_listener"]

    return importlib.import_module("telegram_listener")


def test_parse_signal_message_empty_inputs_return_none():
    mod = _load_parser_module()

    assert mod.parse_signal_message("") is None
    assert mod.parse_signal_message("   ") is None
    assert mod.parse_signal_message(None) is None


def test_parse_signal_message_master_signal_returns_structured_payload():
    mod = _load_parser_module()

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

    res = mod.parse_signal_message(msg)

    assert res is not None
    assert res["market_id"] == "1.123"
    assert res["selection_id"] == 11
    assert res["side"] == "BACK"
    assert res["action"] == "BACK"
    assert float(res["price"]) == 2.10
    assert res["market_type"] == "MATCH_ODDS"


def test_parse_signal_message_legacy_signal_extracts_odds_and_side():
    mod = _load_parser_module()

    msg = "🎯 Juve - Milan\nOver 2.5\n@ 2.10\nStake 10\nPunta"

    res = mod.parse_signal_message(msg)

    assert res is not None
    assert res["market_type"] == "OVER_UNDER"
    assert res["selection"] == "Over 2.5"
    assert res["side"] == "BACK"
    assert res["action"] == "BACK"
    assert float(res["odds"]) == 2.10
    assert float(res["price"]) == 2.10
    assert float(res["stake"]) == 10.0


def test_parse_signal_message_cashout_all_signal():
    mod = _load_parser_module()

    msg = "CASHOUT ALL market_id=1.999"

    res = mod.parse_signal_message(msg)

    assert res is not None
    assert res["market_type"] == "CASHOUT"
    assert res["cashout_type"] == "ALL"


def test_parse_signal_message_invalid_garbage_returns_none():
    mod = _load_parser_module()

    msg = "ciao questo non è un segnale telegram di betting"

    res = mod.parse_signal_message(msg)

    assert res is None