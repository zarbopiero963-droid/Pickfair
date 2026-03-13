from database import Database


def test_saga_insert(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    db.save_saga(
        customer_ref="abc",
        market_id="1.1",
        selection_id="10",
        status="PENDING"
    )

    rows = db.get_pending_sagas()

    assert len(rows) == 1
    assert rows[0]["customer_ref"] == "abc"