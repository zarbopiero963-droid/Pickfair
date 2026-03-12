import pytest

from database import Database


def test_database_execute_commit_and_fetch(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))
    db._set_setting("alpha", "1")
    assert db._get_setting_raw("alpha") == "1"
    db.close()


def test_database_failed_query_does_not_break_subsequent_queries(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    with pytest.raises(Exception):
        db._execute("INSERT INTO table_that_does_not_exist(x) VALUES (1)")

    db._set_setting("beta", "2")
    assert db.get_settings()["beta"] == "2"
    db.close()
