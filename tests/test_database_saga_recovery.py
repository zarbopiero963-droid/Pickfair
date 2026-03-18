from database import Database


def test_saga_lifecycle_pending_to_reconciled(tmp_path):
    db = Database(db_path=str(tmp_path / "saga_reconcile.db"))

    db.create_pending_saga(
        customer_ref="REC-1",
        market_id="1.100",
        selection_id="11",
        payload={"stake": 10.0, "price": 2.5},
    )

    pending_before = db.get_pending_sagas()
    assert len(pending_before) == 1
    assert pending_before[0]["customer_ref"] == "REC-1"

    db.mark_saga_reconciled("REC-1")

    pending_after = db.get_pending_sagas()
    assert pending_after == []

    db.close()


def test_saga_lifecycle_pending_to_failed(tmp_path):
    db = Database(db_path=str(tmp_path / "saga_failed.db"))

    db.create_pending_saga(
        customer_ref="FAIL-1",
        market_id="1.200",
        selection_id="22",
        payload={"stake": 5.0, "price": 3.0},
    )

    pending_before = db.get_pending_sagas()
    assert len(pending_before) == 1
    assert pending_before[0]["customer_ref"] == "FAIL-1"

    db.mark_saga_failed("FAIL-1")

    pending_after = db.get_pending_sagas()
    assert pending_after == []

    db.close()


def test_multiple_pending_sagas_recovery_filters_only_pending(tmp_path):
    db = Database(db_path=str(tmp_path / "saga_multi.db"))

    refs = ["REF-1", "REF-2", "REF-3", "REF-4"]

    for idx, ref in enumerate(refs, start=1):
        db.create_pending_saga(
            customer_ref=ref,
            market_id=f"1.{idx}",
            selection_id=str(idx),
            payload={"stake": idx, "price": 2.0 + idx},
        )

    db.mark_saga_reconciled("REF-1")
    db.mark_saga_failed("REF-2")

    pending = db.get_pending_sagas()
    pending_refs = {row["customer_ref"] for row in pending}

    assert pending_refs == {"REF-3", "REF-4"}

    db.close()


def test_recoverable_saga_payload_is_persisted_and_readable(tmp_path):
    db = Database(db_path=str(tmp_path / "saga_payload.db"))

    payload = {
        "market_id": "1.777",
        "selection_id": 7,
        "stake": 12.5,
        "price": 2.8,
        "bet_type": "BACK",
    }

    db.create_pending_saga(
        customer_ref="PAYLOAD-1",
        market_id="1.777",
        selection_id="7",
        payload=payload,
    )

    pending = db.get_pending_sagas()

    assert len(pending) == 1
    row = pending[0]
    assert row["customer_ref"] == "PAYLOAD-1"
    assert row["market_id"] == "1.777"
    assert str(row["selection_id"]) == "7"
    assert row["raw_payload"]

    db.close()


def test_marking_unknown_saga_is_safe_and_does_not_break_existing_rows(tmp_path):
    db = Database(db_path=str(tmp_path / "saga_unknown.db"))

    db.create_pending_saga(
        customer_ref="KNOWN-1",
        market_id="1.888",
        selection_id="8",
        payload={"stake": 3.0},
    )

    db.mark_saga_reconciled("UNKNOWN-REF")
    db.mark_saga_failed("UNKNOWN-REF")

    pending = db.get_pending_sagas()

    assert len(pending) == 1
    assert pending[0]["customer_ref"] == "KNOWN-1"

    db.close()