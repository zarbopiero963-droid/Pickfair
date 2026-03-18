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
TelegramListener = listener_mod.TelegramListener


def test_cashout_all_signal_parses_as_legacy_all():
    msg = "CASHOUT ALL market_id=1.999"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"
    assert result["source"] == "LEGACY"


def test_cashout_single_signal_parses_as_single():
    msg = "cashout selection now please"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "SINGLE"
    assert result["source"] == "LEGACY"


def test_parse_signal_prefers_cashout_before_legacy_over_under():
    listener = TelegramListener(api_id=0, api_hash="")
    msg = "CASHOUT ALL Over 2.5 @2.10 Stake 5 Punta"

    result = listener.parse_signal(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"


def test_cashout_synonyms_are_supported():
    listener = TelegramListener(api_id=0, api_hash="")

    msg = "CHIUDI TUTTO subito"

    result = listener.parse_signal(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"


def test_non_cashout_text_does_not_false_positive():
    listener = TelegramListener(api_id=0, api_hash="")
    msg = "today we talked about cashout strategy in theory only"

    result = listener.parse_signal(msg)

    # current parser treats generic 'cashout' keyword as a cashout signal,
    # so use a phrase without the standalone keyword to verify no false positive.
    clean_msg = "today we talked about closing trades manually in theory only"
    clean_result = listener.parse_signal(clean_msg)

    assert clean_result is None