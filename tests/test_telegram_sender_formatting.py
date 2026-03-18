from telegram_sender import format_bet_message


def test_format_back_bet_message():
    msg = format_bet_message(
        runner="Juve",
        side="BACK",
        price=2.10,
        stake=10,
        status="MATCHED"
    )

    assert "Juve" in msg
    assert "BACK" in msg
    assert "2.10" in msg
    assert "10" in msg
    assert "MATCHED" in msg


def test_format_lay_bet_message():
    msg = format_bet_message(
        runner="Inter",
        side="LAY",
        price=3.20,
        stake=5,
        status="UNMATCHED"
    )

    assert "LAY" in msg
    assert "3.20" in msg


def test_format_handles_none_runner():
    msg = format_bet_message(
        runner=None,
        side="BACK",
        price=2.5,
        stake=5,
        status="MATCHED"
    )

    assert "Runner" in msg