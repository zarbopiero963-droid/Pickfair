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
TelegramListener = listener_mod.TelegramListener
parse_signal_message = listener_mod.parse_signal_message


def test_parse_master_signal_full_contract():
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
    assert result["action"] == "BACK"
    assert float(result["price"]) == 2.10
    assert result["market_type"] == "MATCH_ODDS"


def test_parse_master_signal_with_noise_lines():
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


def test_parse_master_signal_case_insensitive():
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

    assert result is not None
    assert result["selection_id"] == 11
    assert result["side"] == "BACK"
    assert float(result["price"]) == 2.10


def test_parse_legacy_back_signal():
    msg = "Over 2.5 @2.10 Stake 10 Punta"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "OVER_UNDER"
    assert result["selection"] == "Over 2.5"
    assert result["side"] == "BACK"
    assert result["action"] == "BACK"
    assert float(result["odds"]) == 2.10
    assert float(result["price"]) == 2.10
    assert float(result["stake"]) == 10.0


def test_parse_legacy_lay_signal():
    msg = "Under 2.5 @3.10 Stake 7 Banca"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["market_type"] == "OVER_UNDER"
    assert result["selection"] == "Under 2.5"
    assert result["side"] == "LAY"
    assert result["action"] == "LAY"
    assert float(result["price"]) == 3.10
    assert float(result["stake"]) == 7.0


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


def test_parse_signal_trims_spaces_and_newlines():
    msg = "\n   Over 2.5 @2.20 Stake 5 Punta   \n"

    result = parse_signal_message(msg)

    assert result is not None
    assert result["selection"] == "Over 2.5"
    assert result["side"] == "BACK"
    assert float(result["price"]) == 2.20
    assert float(result["stake"]) == 5.0


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


def test_listener_parse_signal_method_matches_module_level_parser():
    listener = TelegramListener(api_id=0, api_hash="")

    msg = "Over 2.5 @2.20 Stake 5 Punta"

    a = parse_signal_message(msg)
    b = listener.parse_signal(msg)

    assert a == b


def test_listener_parse_signal_prefers_cashout_before_legacy_signal():
    listener = TelegramListener(api_id=0, api_hash="")
    msg = "CASHOUT ALL Over 2.5 @2.10 Stake 5 Punta"

    result = listener.parse_signal(msg)

    assert result is not None
    assert result["market_type"] == "CASHOUT"
    assert result["cashout_type"] == "ALL"