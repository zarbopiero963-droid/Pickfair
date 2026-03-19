

def test_signal_to_order_pipeline(engine):

    payload = {
        "market_id": "1.200",
        "selection_id": 10,
        "bet_type": "BACK",
        "price": 2.2,
        "stake": 5,
        "event_name": "Test Match",
        "market_name": "Match Odds",
        "runner_name": "Runner",
        "simulation_mode": False,
    }

    engine._handle_quick_bet(payload)

    assert True