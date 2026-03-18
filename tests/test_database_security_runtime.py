from database import Database


def test_save_password_roundtrip_and_delete(tmp_path):
    db = Database(db_path=str(tmp_path / "security_password.db"))

    db.save_password("super-secret")
    settings = db.get_settings()

    assert settings["password"] == "super-secret"

    db.save_password(None)
    settings_after_delete = db.get_settings()

    assert "password" not in settings_after_delete

    db.close()


def test_save_password_overwrites_previous_value_cleanly(tmp_path):
    db = Database(db_path=str(tmp_path / "security_password_overwrite.db"))

    db.save_password("first-secret")
    assert db.get_settings()["password"] == "first-secret"

    db.save_password("second-secret")
    settings = db.get_settings()

    assert settings["password"] == "second-secret"

    db.close()


def test_save_and_clear_session_only_removes_session_keys(tmp_path):
    db = Database(db_path=str(tmp_path / "security_session.db"))

    db.save_settings({"theme": "dark", "language": "it"})
    db.save_session("TOKEN-123", expiry="2099-01-01T00:00:00")

    settings = db.get_settings()
    assert settings["session_token"] == "TOKEN-123"
    assert settings["session_expiry"] == "2099-01-01T00:00:00"
    assert settings["theme"] == "dark"

    db.clear_session()

    cleared = db.get_settings()
    assert "session_token" not in cleared
    assert "session_expiry" not in cleared
    assert cleared["theme"] == "dark"
    assert cleared["language"] == "it"

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


def test_sql_injection_like_text_is_stored_as_data_not_executed(tmp_path):
    db = Database(db_path=str(tmp_path / "security_injection.db"))

    evil_text = "abc'); DROP TABLE settings; --"

    db.save_settings({"nickname": evil_text})
    db.save_telegram_chat(chat_id="1", title=evil_text, username="user", is_active=True)
    db.save_signal_pattern(pattern=evil_text, label="inj", enabled=True)

    settings = db.get_settings()
    chats = db.get_telegram_chats()
    patterns = db.get_signal_patterns()

    assert settings["nickname"] == evil_text
    assert len(chats) == 1
    assert chats[0]["title"] == evil_text
    assert len(patterns) == 1
    assert patterns[0]["pattern"] == evil_text

    db.save_settings({"still_ok": "yes"})
    after = db.get_settings()
    assert after["still_ok"] == "yes"

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

    db.save_settings({"still_alive": "yes"})
    assert db.get_settings()["still_alive"] == "yes"

    db.close()


def test_create_pending_saga_stores_hash_and_raw_payload_consistently(tmp_path):
    db = Database(db_path=str(tmp_path / "security_saga_hash.db"))

    payload = {
        "market_id": "1.123",
        "selection_id": 10,
        "stake": 5.0,
        "price": 2.2,
    }

    db.create_pending_saga(
        customer_ref="SEC-REF-1",
        market_id="1.123",
        selection_id="10",
        payload=payload,
    )

    pending = db.get_pending_sagas()

    assert len(pending) == 1
    row = pending[0]
    assert row["customer_ref"] == "SEC-REF-1"
    assert row["raw_payload"]
    assert row["payload_hash"]
    assert len(row["payload_hash"]) == 64

    db.close()


def test_outbox_log_stringifies_error_and_message_id_safely(tmp_path):
    db = Database(db_path=str(tmp_path / "security_outbox.db"))

    db.save_telegram_outbox_log(
        chat_id=123,
        message_type="ALERT",
        text="hello",
        status="FAILED",
        message_id=999,
        error=ValueError("network exploded"),
        flood_wait="15",
    )

    rows = db.get_telegram_outbox_log(limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row["chat_id"] == "123"
    assert row["message_type"] == "ALERT"
    assert row["text"] == "hello"
    assert row["status"] == "FAILED"
    assert row["message_id"] == "999"
    assert "network exploded" in row["error"]
    assert int(row["flood_wait"]) == 15

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
    ids = {row["message_id"] for row in rows}
    assert ids == {"100", "101"}

    failed = [row for row in rows if row["status"] == "FAILED"][0]
    assert failed["chat_id"] == "2"
    assert failed["message_type"] == "ERROR"
    assert failed["text"] == "boom"
    assert "network down" in failed["error"]
    assert str(failed["flood_wait"]) == "10"

    db.close()