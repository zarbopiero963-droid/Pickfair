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

    # prove tables still exist and are usable
    db.save_settings({"still_ok": "yes"})
    after = db.get_settings()
    assert after["still_ok"] == "yes"

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