from database import Database


def test_default_simulation_settings_are_seeded(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_defaults.db"))

    settings = db.get_simulation_settings()

    assert settings["virtual_balance"] == 1000.0
    assert settings["starting_balance"] == 1000.0
    assert settings["bet_count"] == 0

    db.close()


def test_increment_simulation_bet_count_updates_balance_and_counter(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_counter.db"))

    before = db.get_simulation_settings()
    assert before["bet_count"] == 0
    assert before["virtual_balance"] == 1000.0

    db.increment_simulation_bet_count(987.5)

    after = db.get_simulation_settings()
    assert after["bet_count"] == 1
    assert after["virtual_balance"] == 987.5
    assert after["starting_balance"] == 1000.0

    db.close()


def test_multiple_simulation_updates_preserve_latest_balance_and_count(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_progress.db"))

    balances = [990.0, 980.5, 1002.0, 975.25]
    for balance in balances:
        db.increment_simulation_bet_count(balance)

    settings = db.get_simulation_settings()

    assert settings["bet_count"] == 4
    assert settings["virtual_balance"] == 975.25
    assert settings["starting_balance"] == 1000.0

    db.close()


def test_save_simulation_bet_persists_runtime_history_row(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_history.db"))

    db.save_simulation_bet(
        event_name="Juve - Milan",
        market_id="1.777",
        market_name="Match Odds",
        side="BACK",
        selection_id=11,
        selection_name="Juve",
        price=2.4,
        stake=10.0,
        status="MATCHED",
        selections=[{"selectionId": 11, "price": 2.4, "stake": 10.0}],
        total_stake=10.0,
        potential_profit=14.0,
    )

    rows = db.get_simulation_bet_history(limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row["event_name"] == "Juve - Milan"
    assert row["market_id"] == "1.777"
    assert row["market_name"] == "Match Odds"
    assert row["side"] == "BACK"
    assert str(row["selection_id"]) == "11"
    assert row["selection_name"] == "Juve"
    assert float(row["price"]) == 2.4
    assert float(row["stake"]) == 10.0
    assert row["status"] == "MATCHED"
    assert isinstance(row["selections"], list)
    assert row["selections"][0]["selectionId"] == 11
    assert float(row["total_stake"]) == 10.0
    assert float(row["potential_profit"]) == 14.0

    db.close()


def test_add_simulated_bet_alias_behaves_like_save_simulation_bet(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_alias.db"))

    db.add_simulated_bet(
        event_name="Inter - Roma",
        market_id="1.888",
        market_name="Match Odds",
        side="LAY",
        selection_id=22,
        selection_name="Roma",
        price=3.1,
        stake=6.0,
        status="MATCHED",
        selections=[{"selectionId": 22, "price": 3.1, "stake": 6.0}],
        total_stake=6.0,
        potential_profit=4.0,
    )

    rows = db.get_simulation_bets(limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row["market_id"] == "1.888"
    assert row["side"] == "LAY"
    assert row["selection_name"] == "Roma"
    assert float(row["stake"]) == 6.0

    db.close()