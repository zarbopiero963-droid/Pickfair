from database import Database


def test_database_insert_and_read(tmp_path):
    db_path = tmp_path / "db.sqlite"

    db = Database(str(db_path))

    db.save_telegram_settings(api_id="123", api_hash="abc")

    settings = db.get_telegram_settings()

    assert settings["api_id"] == "123"
    assert settings["api_hash"] == "abc"


def test_database_remove_password(tmp_path):
    db_path = tmp_path / "db.sqlite"

    db = Database(str(db_path))

    db.save_password("secret")
    assert "password" in db.get_settings()

    db.save_password(None)

    settings = db.get_settings()

    assert "password" not in settings