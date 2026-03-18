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


def test_database_concurrent_telegram_settings_merges_without_losing_fields(tmp_path):
    db = Database(db_path=str(tmp_path / "telegram.db"))

    payloads = [
        {"api_id": "100", "api_hash": "hashA"},
        {"phone_number": "+39000", "enabled": True},
        {"auto_bet": True, "require_confirmation": False},
        {"auto_stake": 3.5, "master_chat_id": "111"},
        {"publisher_chat_id": "222", "session_string": "SESSION"},
    ]

    threads = [threading.Thread(target=db.save_telegram_settings, kwargs={"settings": p}) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    settings = db.get_telegram_settings()

    assert settings["api_id"] == "100"
    assert settings["api_hash"] == "hashA"
    assert settings["phone_number"] == "+39000"
    assert settings["enabled"] is True
    assert settings["auto_bet"] is True
    assert settings["require_confirmation"] is False
    assert settings["auto_stake"] == 3.5
    assert settings["master_chat_id"] == "111"
    assert settings["publisher_chat_id"] == "222"
    assert settings["session_string"] == "SESSION"

    db.close()


def test_database_concurrent_pending_saga_inserts_are_all_visible(tmp_path):
    db = Database(db_path=str(tmp_path / "saga.db"))

    def worker(idx):
        db.create_pending_saga(
            customer_ref=f"REF-{idx}",
            market_id="1.999",
            selection_id=str(idx),
            payload={"stake": idx, "selection_id": idx},
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    pending = db.get_pending_sagas()
    refs = {row["customer_ref"] for row in pending}

    assert len(pending) == 25
    assert refs == {f"REF-{i}" for i in range(25)}

    db.close()


def test_database_concurrent_bet_history_writes_preserve_all_rows(tmp_path):
    db = Database(db_path=str(tmp_path / "bets.db"))

    def worker(idx):
        db.save_bet(
            event_name=f"Event {idx}",
            market_id=f"1.{idx}",
            market_name="Match Odds",
            bet_type="BACK",
            selections=[{"selectionId": idx, "price": 2.0, "stake": 5.0}],
            total_stake=5.0,
            potential_profit=5.0,
            status="MATCHED",
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    bets = db.get_bet_history(limit=100)
    market_ids = {row["market_id"] for row in bets}

    assert len(bets) == 20
    assert market_ids == {f"1.{i}" for i in range(20)}

    db.close()