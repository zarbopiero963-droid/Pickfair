import os
import pytest
from database import Database

@pytest.fixture
def db():
    db_instance = Database()
    yield db_instance
    db_path = db_instance.db_path
    db_instance.close()

    for suffix in ("", "-wal", "-shm"):
        path = f"{db_path}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def test_db_settings_legacy(db):
    db.save_settings({"theme": "dark", "version": "1.0"})
    assert db.get_settings()["theme"] == "dark"

    db.save_password("pass123")
    db.save_session("tok123", "exp123")

    settings = db.get_settings()
    assert settings["password"] == "pass123"
    assert settings["session_token"] == "tok123"

    db.clear_session()
    assert "session_token" not in db.get_settings()

    db.save_password(None)
    assert "password" not in db.get_settings()

def test_db_telegram_settings_dict_and_kwargs(db):
    db.save_telegram_settings(api_id="123", api_hash="abc", master_chat_id="-100")
    assert db.get_telegram_settings()["api_id"] == "123"
    assert db.get_telegram_settings()["master_chat_id"] == "-100"

    db.save_telegram_settings({"api_id": "456", "enabled": 1})
    assert db.get_telegram_settings()["api_id"] == "456"

def test_db_telegram_chats_and_patterns(db):
    db.save_telegram_chat("1", "test_chat", username="test_usr")
    chats = db.get_telegram_chats()
    assert len(chats) == 1
    assert chats[0]["username"] == "test_usr"

    db.replace_telegram_chats([{"chat_id": "2", "title": "new"}])
    assert db.get_telegram_chats()[0]["chat_id"] == "2"

    db.delete_telegram_chat("2")
    assert len(db.get_telegram_chats()) == 0

    db.save_signal_pattern("REGEX", "Label", True)
    assert len(db.get_signal_patterns(enabled_only=True)) == 1

    patterns = db.get_signal_patterns()
    db.toggle_signal_pattern(patterns[0]["id"])
    assert len(db.get_signal_patterns(enabled_only=True)) == 0

def test_db_sagas_and_bets(db):
    db.create_pending_saga("ref1", "mkt1", "sel1", {"test": True})
    assert len(db.get_pending_sagas()) == 1

    db.mark_saga_reconciled("ref1")
    assert len(db.get_pending_sagas()) == 0

    db.save_bet("ev", "mkt", "name", "BACK", [], 10.0, 5.0)
    assert len(db.get_bet_history()) == 1
    assert db.get_active_bets_count() == 1
    assert db.get_today_profit_loss() == 5.0

def test_db_simulation_and_outbox(db):
    db.add_simulated_bet("ev", "mkt", "name", "BACK", "1", "sel", 2.0, 10.0)
    assert len(db.get_simulation_bet_history()) == 1

    db.save_telegram_outbox_log("-1001", "MASTER_SIGNAL", "hello", "SENT", message_id="99")
    rows = db.get_telegram_outbox_log()
    assert len(rows) == 1
    assert rows[0]["status"] == "SENT"

