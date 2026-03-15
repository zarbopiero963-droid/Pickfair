PAYLOAD = {
    "market_id": "1.123",
    "selectionId": 101,
    "price": 2.5,
    "stake": 10
}


SYSTEM_PAYLOAD = {
    "source": "pickfair",
    "market_id": "1.123",
    "market_type": "MATCH_ODDS",
    "event_name": "Sample Event",
    "market_name": "Match Odds",
    "results": [
        {
            "selectionId": 101,
            "runnerName": "Runner 1",
            "price": 2.5,
            "stake": 10,
            "side": "BACK",
            "effectiveType": "BACK",
        }
    ],
    "bet_type": "SINGLE",
    "total_stake": 10,
    "use_best_price": True,
    "simulation_mode": False,
    "auto_green": False,
    "stop_loss": 0,
    "take_profit": 0,
    "trailing": False,
    "preflight": {
        "is_valid": True,
        "warnings": [],
        "errors": [],
        "details": {},
    },
    "analytics": {
        "potential_profit": 15.0,
        "implied_probability": 0.4,
    },
}