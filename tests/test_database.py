from database import Database


def test_database_settings_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "settings.db"))

    payload = {
        "theme": "dark",
        "language": "it",
        "timezone": "Europe/Rome",
    }

    db.save_settings(payload)
    settings = db.get_settings()

    assert settings["theme"] == "dark"
    assert settings["language"] == "it"
    assert settings["timezone"] == "Europe/Rome"

    db.close()


def test_database_telegram_settings_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "telegram.db"))

    payload = {
        "api_id": "123",
        "api_hash": "hash123",
        "phone_number": "+391234567890",
        "enabled": True,
        "auto_bet": True,
        "require_confirmation": False,
        "auto_stake": 2.5,
        "master_chat_id": "111",
        "publisher_chat_id": "222",
    }

    db.save_telegram_settings(payload)
    settings = db.get_telegram_settings()

    assert settings["api_id"] == "123"
    assert settings["api_hash"] == "hash123"
    assert settings["phone_number"] == "+391234567890"
    assert settings["enabled"] is True
    assert settings["auto_bet"] is True
    assert settings["require_confirmation"] is False
    assert settings["auto_stake"] == 2.5
    assert settings["master_chat_id"] == "111"
    assert settings["publisher_chat_id"] == "222"

    db.close()


def test_database_pending_saga_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "sagas.db"))

    db.create_pending_saga(
        customer_ref="REF-1",
        market_id="1.123",
        selection_id="10",
        payload={"stake": 5.0, "price": 2.1},
    )

    pending = db.get_pending_sagas()

    assert len(pending) == 1
    assert pending[0]["customer_ref"] == "REF-1"
    assert pending[0]["market_id"] == "1.123"
    assert str(pending[0]["selection_id"]) == "10"
    assert pending[0]["raw_payload"]

    db.close()


def test_database_save_bet_and_read_history(tmp_path):
    db = Database(db_path=str(tmp_path / "bets.db"))

    db.save_bet(
        event_name="Juve - Milan",
        market_id="1.999",
        market_name="Match Odds",
        bet_type="BACK",
        selections=[{"selectionId": 11, "price": 2.3, "stake": 10.0}],
        total_stake=10.0,
        potential_profit=13.0,
        status="MATCHED",
    )

    history = db.get_bet_history(limit=10)

    assert len(history) == 1
    assert history[0]["event_name"] == "Juve - Milan"
    assert history[0]["market_id"] == "1.999"
    assert history[0]["bet_type"] == "BACK"
    assert history[0]["status"] == "MATCHED"

    db.close()


def test_database_pending_saga_mark_reconciled_removes_from_pending(tmp_path):
    db = Database(db_path=str(tmp_path / "reconcile.db"))

    db.create_pending_saga(
        customer_ref="REF-REC",
        market_id="1.555",
        selection_id="55",
        payload={"stake": 4.0},
    )

    assert len(db.get_pending_sagas()) == 1

    db.mark_saga_reconciled("REF-REC")

    assert db.get_pending_sagas() == []

    db.close()