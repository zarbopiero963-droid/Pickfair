import pytest

from database import Database


def test_outbox_log_insert(tmp_path):
    db = Database(str(tmp_path / "test.db"))

    db.log_telegram_outbox("test message")

    logs = db.get_telegram_outbox_log()

    assert isinstance(logs, list)