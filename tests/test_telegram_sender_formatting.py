def format_bet_message(
    runner: str = None,
    side: str = None,
    price: float = 0.0,
    stake: float = 0.0,
    market_id: str = "",
    selection_id: str = "",
    event_name: str = "",
    market_name: str = "",
    status: str = "MATCHED",
    **kwargs,
) -> str:
    # compatibilità nomi vecchi/nuovi
    runner_name = runner if runner is not None else kwargs.get("runner_name")
    action = side if side is not None else kwargs.get("action")

    # fallback richiesto dai test
    if runner_name is None:
        runner_name = "Runner"

    safe_runner = str(runner_name)
    safe_action = "" if action is None else str(action).upper().strip()
    safe_market_id = "" if market_id is None else str(market_id)
    safe_selection_id = "" if selection_id is None else str(selection_id)
    safe_event_name = "" if event_name is None else str(event_name)
    safe_market_name = "" if market_name is None else str(market_name)
    safe_status = "" if status is None else str(status)

    try:
        safe_price = float(price)
    except Exception:
        safe_price = 0.0

    try:
        safe_stake = float(stake)
    except Exception:
        safe_stake = 0.0

    return (
        "🟢 MASTER SIGNAL\n\n"
        f"event_name: {safe_event_name}\n"
        f"market_name: {safe_market_name}\n"
        f"selection: {safe_runner}\n"
        f"action: {safe_action}\n"
        f"master_price: {safe_price:.2f}\n"
        f"stake: {safe_stake:.2f}\n"
        f"market_id: {safe_market_id}\n"
        f"selection_id: {safe_selection_id}\n"
        f"status: {safe_status}"
    )