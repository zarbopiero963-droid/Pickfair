from database import Database


def test_database_initialization(tmp_path):
    db_path = tmp_path / "test.sqlite"

    db = Database(str(db_path))

    settings = db.get_settings()

    assert isinstance(settings, dict)


def test_database_password_storage(tmp_path):
    db_path = tmp_path / "test.sqlite"

    db = Database(str(db_path))

    db.save_password("secret")

    settings = db.get_settings()

    assert settings["password"] == "secret"