from database import Database


def test_saga_insert(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    saga = db.create_pending_saga("1.1")

    assert saga is not None