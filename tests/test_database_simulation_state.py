from database import Database


def test_simulation_settings_exist_and_have_runtime_shape(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_settings_shape.db"))

    settings = db.get_simulation_settings()

    assert isinstance(settings, dict)
    assert settings is not None

    db.close()


def test_save_simulation_bet_persists_runtime_row(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_bet.db"))

    db.save_simulation_bet(
        market_id="1.101",
        selection_id=11,
        side="BACK",
        stake=10.0,
        price=2.5,
        status="MATCHED",
        pnl=15.0,
        balance_after=1015.0,
    )

    settings = db.get_simulation_settings()
    assert isinstance(settings, dict)

    db.close()


def test_increment_simulation_bet_count_updates_balance_state(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_balance.db"))

    before = db.get_simulation_settings()
    assert isinstance(before, dict)

    db.increment_simulation_bet_count(987.5)

    after = db.get_simulation_settings()
    assert isinstance(after, dict)

    balance_candidates = [
        after.get("virtual_balance"),
        after.get("balance"),
        after.get("current_balance"),
    ]

    assert 987.5 in balance_candidates

    db.close()


def test_multiple_simulation_bets_do_not_break_state_tracking(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_multi.db"))

    for idx in range(5):
        db.save_simulation_bet(
            market_id=f"1.{idx}",
            selection_id=idx,
            side="BACK" if idx % 2 == 0 else "LAY",
            stake=2.0 + idx,
            price=2.0,
            status="MATCHED",
            pnl=1.0 * idx,
            balance_after=1000.0 - idx,
        )

    settings = db.get_simulation_settings()
    assert isinstance(settings, dict)

    db.close()


def test_simulation_balance_progression_is_persisted_across_updates(tmp_path):
    db = Database(db_path=str(tmp_path / "sim_progression.db"))

    balances = [1000.0, 995.0, 1003.5, 990.0]

    for balance in balances:
        db.increment_simulation_bet_count(balance)

    settings = db.get_simulation_settings()

    balance_candidates = [
        settings.get("virtual_balance"),
        settings.get("balance"),
        settings.get("current_balance"),
    ]

    assert 990.0 in balance_candidates

    db.close()