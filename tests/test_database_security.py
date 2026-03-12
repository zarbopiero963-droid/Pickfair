from database import Database


def test_clear_session(tmp_path):

    db = Database(db_path=str(tmp_path / "test.db"))

    db.save_session("abc", "exp")

    db.clear_session()

    settings = db.get_settings()

    assert "session_token" not in settings


def test_save_password_none(tmp_path):

    db = Database(db_path=str(tmp_path / "test.db"))

    db.save_password("123")

    db.save_password(None)

    settings = db.get_settings()

    assert "password" not in settings