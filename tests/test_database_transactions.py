from database import Database


def test_database_transaction_commit_persists_multiple_operations(tmp_path):
    db = Database(db_path=str(tmp_path / "tx_commit.db"))

    with db.transaction():
        db.save_settings({"theme": "dark", "language": "it"})
        db.save_telegram_settings(
            {
                "api_id": "123",
                "api_hash": "hash123",
                "phone_number": "+391234567890",
                "enabled": True,
            }
        )
        db.create_pending_saga(
            customer_ref="REF-COMMIT-1",
            market_id="1.100",
            selection_id="11",
            payload={"stake": 10.0, "price": 2.5},
        )

    settings = db.get_settings()
    telegram = db.get_telegram_settings()
    pending = db.get_pending_sagas()

    assert settings["theme"] == "dark"
    assert settings["language"] == "it"

    assert telegram["api_id"] == "123"
    assert telegram["api_hash"] == "hash123"
    assert telegram["phone_number"] == "+391234567890"
    assert telegram["enabled"] is True

    assert len(pending) == 1
    assert pending[0]["customer_ref"] == "REF-COMMIT-1"
    assert pending[0]["market_id"] == "1.100"

    db.close()


def test_database_transaction_rollback_reverts_all_operations(tmp_path):
    db = Database(db_path=str(tmp_path / "tx_rollback.db"))

    db.save_settings({"existing": "keep"})

    try:
        with db.transaction():
            db.save_settings({"theme": "light"})
            db.save_telegram_settings(
                {
                    "api_id": "999",
                    "api_hash": "should_not_persist",
                }
            )
            db.create_pending_saga(
                customer_ref="REF-ROLLBACK-1",
                market_id="1.200",
                selection_id="22",
                payload={"stake": 5.0},
            )
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    settings = db.get_settings()
    telegram = db.get_telegram_settings()
    pending = db.get_pending_sagas()

    assert settings["existing"] == "keep"
    assert "theme" not in settings

    assert telegram.get("api_id") in (None, "", 0, False)
    assert telegram.get("api_hash") in (None, "")

    assert pending == []

    db.close()


def test_database_nested_transaction_keeps_single_atomic_commit(tmp_path):
    db = Database(db_path=str(tmp_path / "tx_nested.db"))

    with db.transaction():
        db.save_settings({"outer": "yes"})
        with db.transaction():
            db.save_settings({"inner": "yes"})
            db.save_telegram_settings(
                {
                    "phone_number": "+39000",
                    "enabled": True,
                }
            )

    settings = db.get_settings()
    telegram = db.get_telegram_settings()

    assert settings["outer"] == "yes"
    assert settings["inner"] == "yes"
    assert telegram["phone_number"] == "+39000"
    assert telegram["enabled"] is True

    db.close()


def test_database_transaction_commit_persists_bet_and_history_row(tmp_path):
    db = Database(db_path=str(tmp_path / "tx_bet.db"))

    with db.transaction():
        db.save_bet(
            event_name="Juve - Milan",
            market_id="1.300",
            market_name="Match Odds",
            bet_type="BACK",
            selections=[{"selectionId": 11, "price": 2.2, "stake": 10.0}],
            total_stake=10.0,
            potential_profit=12.0,
            status="MATCHED",
        )

    history = db.get_bet_history(limit=10)

    assert len(history) == 1
    assert history[0]["event_name"] == "Juve - Milan"
    assert history[0]["market_id"] == "1.300"
    assert history[0]["bet_type"] == "BACK"
    assert history[0]["status"] == "MATCHED"

    db.close()


def test_database_transaction_rollback_prevents_partial_bet_history_write(tmp_path):
    db = Database(db_path=str(tmp_path / "tx_bet_rollback.db"))

    try:
        with db.transaction():
            db.save_bet(
                event_name="Inter - Roma",
                market_id="1.400",
                market_name="Match Odds",
                bet_type="LAY",
                selections=[{"selectionId": 22, "price": 3.0, "stake": 6.0}],
                total_stake=6.0,
                potential_profit=4.0,
                status="MATCHED",
            )
            raise ValueError("abort")
    except ValueError:
        pass

    history = db.get_bet_history(limit=10)
    assert history == []

    db.close()