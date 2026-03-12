from database import Database


def test_database_clear_session_removes_keys(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    db.save_session("tok123", "exp123")
    settings_before = db.get_settings()

    assert settings_before["session_token"] == "tok123"
    assert settings_before["session_expiry"] == "exp123"

    db.clear_session()
    settings_after = db.get_settings()

    assert "session_token" not in settings_after
    assert "session_expiry" not in settings_after


def test_database_save_password_none_removes_key(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    db.save_password("pass123")
    assert db.get_settings()["password"] == "pass123"

    db.save_password(None)
    settings = db.get_settings()

    assert "password" not in settings