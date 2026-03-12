import pytest

from database import Database


def test_database_initialization(tmp_path):
    db = Database(str(tmp_path / "test.db"))

    assert db is not None