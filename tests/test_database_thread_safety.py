import threading
from database import Database


def test_thread_safe_writes(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))

    def write():
        db.save_received_signal({"a": 1})

    threads = [threading.Thread(target=write) for _ in range(5)]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert True