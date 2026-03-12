from database import Database


def test_database_saga_recovery_flow(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    db.create_pending_saga("ref-1", "1.1", "11", {"stake": 5})
    pending = db.get_pending_sagas()
    assert len(pending) == 1
    assert pending[0]["customer_ref"] == "ref-1"

    db.mark_saga_reconciled("ref-1")
    assert db.get_pending_sagas() == []

    db.create_pending_saga("ref-2", "1.2", "22", {"stake": 10})
    db.mark_saga_failed("ref-2")
    assert db.get_pending_sagas() == []

    db.close()
