def test_safe_mode_blocks_orders(engine, broker):

    engine._toggle_kill_switch({"enabled": True})

    engine._handle_quick_bet(
        {
            "market_id": "1.200",
            "selection_id": 10,
            "bet_type": "BACK",
            "price": 2.2,
            "stake": 5,
            "event_name": "Test",
            "market_name": "Odds",
            "runner_name": "Runner",
            "simulation_mode": False,
        }
    )

    assert broker.orders == []