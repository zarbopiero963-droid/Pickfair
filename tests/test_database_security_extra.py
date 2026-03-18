from database import Database


def test_save_password_overwrites_previous_value_cleanly(tmp_path):
    db = Database(db_path=str(tmp_path / "security_password_overwrite.db"))

    db.save_password("first-secret")
    assert db.get_settings()["password"] == "first-secret"

    db.save_password("second-secret")
    settings = db.get_settings()

    assert settings["password"] == "second-secret"

    db.close()


def test_clear_session_is_idempotent(tmp_path):
    db = Database(db_path=str(tmp_path / "security_clear_session.db"))

    db.save_session("TOKEN-1", expiry="2099-01-01T00:00:00")
    db.clear_session()
    db.clear_session()

    settings = db.get_settings()

    assert "session_token" not in settings
    assert "session_expiry" not in settings

    db.close()


def test_telegram_chat_fields_store_html_and_quotes_safely(tmp_path):
    db = Database(db_path=str(tmp_path / "security_chat_strings.db"))

    weird_title = '<b>"Admin"</b> & friends'
    weird_username = "user_'_x"

    db.save_telegram_chat(
        chat_id="777",
        title=weird_title,
        username=weird_username,
        is_active=True,
    )

    chats = db.get_telegram_chats()

    assert len(chats) == 1
    assert chats[0]["chat_id"] == "777"
    assert chats[0]["title"] == weird_title
    assert chats[0]["username"] == weird_username
    assert chats[0]["is_active"] is True

    db.close()


def test_signal_patterns_can_store_regex_like_text_without_breaking_tables(tmp_path):
    db = Database(db_path=str(tmp_path / "security_patterns.db"))

    pattern = r"(?i)BACK\s+@\d+\.\d+\s+stake\s+\d+"
    label = "regex-pattern"

    db.save_signal_pattern(pattern=pattern, label=label, enabled=True)

    patterns = db.get_signal_patterns()

    assert len(patterns) == 1
    assert patterns[0]["pattern"] == pattern
    assert patterns[0]["label"] == label
    assert patterns[0]["enabled"] is True

    # sanity check: DB still usable after regex-like payloads
    db.save_settings({"still_alive": "yes"})
    assert db.get_settings()["still_alive"] == "yes"

    db.close()


def test_outbox_log_multiple_rows_preserve_order_and_values(tmp_path):
    db = Database(db_path=str(tmp_path / "security_outbox_multi.db"))

    db.save_telegram_outbox_log(
        chat_id="1",
        message_type="INFO",
        text="hello",
        status="SENT",
        message_id="100",
        error=None,
        flood_wait=None,
    )
    db.save_telegram_outbox_log(
        chat_id="2",
        message_type="ERROR",
        text="boom",
        status="FAILED",
        message_id="101",
        error="network down",
        flood_wait="10",
    )

    rows = db.get_telegram_outbox_log(limit=10)

    assert len(rows) == 2
    assert rows[0]["message_id"] in {"100", "101"}
    ids = {row["message_id"] for row in rows}
    assert ids == {"100", "101"}

    failed = [row for row in rows if row["status"] == "FAILED"][0]
    assert failed["chat_id"] == "2"
    assert failed["message_type"] == "ERROR"
    assert failed["text"] == "boom"
    assert "network down" in failed["error"]
    assert str(failed["flood_wait"]) == "10"

    db.close()