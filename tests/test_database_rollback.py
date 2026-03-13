import pytest

from database import Database


def test_transaction_rollback_keeps_database_usable(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    before = db.get_settings()
    assert isinstance(before, dict)

    with pytest.raises(Exception):
        db._execute("INSERT INTO not_existing_table (x) VALUES (?)", (1,))

    db.save_password("secret")
    settings = db.get_settings()

    assert settings["password"] == "secret"