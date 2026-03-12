from telegram_listener import parse_signal_message


def test_parse_master_signal():

    msg = """
MATCH: Juventus - Milan
BET: BACK Juventus
PRICE: 2.10
STAKE: 10
"""

    result = parse_signal_message(msg)

    assert result is not None
    assert result["action"] == "BACK"


def test_parse_legacy_signal():

    msg = "Punta Juventus quota 2.10 stake 10"

    result = parse_signal_message(msg)

    assert result is not None