import threading

from database import Database


def test_database_thread_safe_settings_roundtrip(tmp_path):
    db = Database(db_path=str(tmp_path / "threadsafe_settings.db"))

    def worker(idx):
        db.save_settings({f"k_{idx}": f"v_{idx}"})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    settings = db.get_settings()

    for i in range(15):
        assert settings[f"k_{i}"] == f"v_{i}"

    db.close()


def test_database_thread_safe_pending_saga_updates(tmp_path):
    db = Database(db_path=str(tmp_path / "threadsafe_sagas.db"))

    def create_worker(idx):
        db.create_pending_saga(
            customer_ref=f"REF-{idx}",
            market_id="1.900",
            selection_id=str(idx),
            payload={"selection_id": idx, "stake": 5.0},
        )

    create_threads = [threading.Thread(target=create_worker, args=(i,)) for i in range(20)]
    for thread in create_threads:
        thread.start()
    for thread in create_threads:
        thread.join()

    pending = db.get_pending_sagas()
    assert len(pending) == 20

    def reconcile_worker(idx):
        db.mark_saga_reconciled(f"REF-{idx}")

    reconcile_threads = [threading.Thread(target=reconcile_worker, args=(i,)) for i in range(10)]
    for thread in reconcile_threads:
        thread.start()
    for thread in reconcile_threads:
        thread.join()

    still_pending = db.get_pending_sagas()
    refs = {row["customer_ref"] for row in still_pending}

    assert len(still_pending) == 10
    assert refs == {f"REF-{i}" for i in range(10, 20)}

    db.close()


def test_database_thread_safe_bet_history_inserts(tmp_path):
    db = Database(db_path=str(tmp_path / "threadsafe_bets.db"))

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

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    history = db.get_bet_history(limit=100)
    market_ids = {row["market_id"] for row in history}

    assert len(history) == 25
    assert market_ids == {f"1.{i}" for i in range(25)}

    db.close()


def test_database_thread_safe_telegram_settings_merge(tmp_path):
    db = Database(db_path=str(tmp_path / "threadsafe_telegram.db"))

    payloads = [
        {"api_id": "100"},
        {"api_hash": "HASH"},
        {"phone_number": "+39123"},
        {"enabled": True},
        {"auto_bet": True},
        {"require_confirmation": False},
        {"auto_stake": 2.5},
        {"master_chat_id": "111"},
        {"publisher_chat_id": "222"},
        {"session_string": "SESSION"},
    ]

    threads = [
        threading.Thread(target=db.save_telegram_settings, kwargs={"settings": payload})
        for payload in payloads
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    settings = db.get_telegram_settings()

    assert settings["api_id"] == "100"
    assert settings["api_hash"] == "HASH"
    assert settings["phone_number"] == "+39123"
    assert settings["enabled"] is True
    assert settings["auto_bet"] is True
    assert settings["require_confirmation"] is False
    assert settings["auto_stake"] == 2.5
    assert settings["master_chat_id"] == "111"
    assert settings["publisher_chat_id"] == "222"
    assert settings["session_string"] == "SESSION"

    db.close()


def test_database_thread_safe_simulation_state_updates(tmp_path):
    db = Database(db_path=str(tmp_path / "threadsafe_sim.db"))

    def worker(idx):
        db.save_simulation_bet(
            market_id=f"1.{idx}",
            selection_id=idx,
            side="BACK",
            stake=2.0,
            price=2.0,
            status="MATCHED",
            pnl=1.0,
            balance_after=1000.0 - idx,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    settings = db.get_simulation_settings()
    assert settings is not None

    db.close()