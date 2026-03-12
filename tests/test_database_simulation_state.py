import pytest

from database import Database


def test_simulation_settings(tmp_path):
    db = Database(str(tmp_path / "test.db"))

    settings = db.get_simulation_settings()

    assert isinstance(settings, dict)