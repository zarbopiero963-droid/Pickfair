from database import Database


def test_recover_pending_saga(tmp_path):

    db = Database(db_path=str(tmp_path / "test.db"))

    db.create_pending_saga(
        "ref1",
        "1.1",
        "123",
        {"side": "BACK"}
    )

    sagas = db.get_pending_sagas()

    assert len(sagas) == 1

    db.mark_saga_reconciled("ref1")

    sagas = db.get_pending_sagas()

    assert len(sagas) == 0