import threading

from database import Database


def test_database_concurrent_settings_writes(tmp_path):
    db = Database(db_path=str(tmp_path / "test.db"))

    def worker(idx):
        db.save_settings({f"key_{idx}": f"value_{idx}"})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    settings = db.get_settings()
    for i in range(10):
        assert settings[f"key_{i}"] == f"value_{i}"

    db.close()
