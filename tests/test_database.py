import os
import pytest
from database import Database

@pytest.fixture
def db():
    db_instance = Database()
    yield db_instance
    db_instance.close()
    if os.path.exists(db_instance.db_path):
        try: os.remove(db_instance.db_path)
        except: pass

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
    # Test Kwargs vecchi
    db.save_telegram_settings(api_id="123", api_hash="abc", master_chat_id="-100")
    assert db.get_telegram_settings()["api_id"] == "123"
    assert db.get_telegram_settings()["master_chat_id"] == "-100"
    # Test Dict nuovo
    db.save_telegram_settings({"api_id": "456", "enabled": 1})
    assert db.get_telegram_settings()["api_id"] == "456"

def test_db_telegram_chats_and_patterns(db):
    db.save_telegram_chat("1", "test_chat", username="test_usr")
    assert len(db.get_telegram_chats()) == 1
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

    # Simulazione legacy alias
    db.add_simulated_bet("ev", "mkt", "name", "BACK", "1", "sel", 2.0, 10.0)
    assert len(db.get_simulation_bet_history()) == 1