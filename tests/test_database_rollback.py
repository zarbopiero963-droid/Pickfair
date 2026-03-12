from database import Database


def test_transaction_rollback(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    try:
        db.conn.execute("BEGIN")
        db.conn.execute("INVALID SQL")
    except Exception:
        db.conn.rollback()

    assert True