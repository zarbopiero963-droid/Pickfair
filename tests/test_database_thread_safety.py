import threading

from database import Database


def test_thread_safe_writes_insert_all_signals(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    def write(idx: int):
        db.save_received_signal(
            selection=f"Runner {idx}",
            action="BACK",
            price=2.0 + idx,
            stake=10.0,
            status="NEW",
        )

    threads = [threading.Thread(target=write, args=(i,)) for i in range(5)]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    rows = db.get_received_signals(limit=10)

    assert len(rows) == 5
    assert all(row["status"] == "NEW" for row in rows)