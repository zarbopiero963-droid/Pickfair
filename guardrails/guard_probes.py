from typing import Any, Dict, List

from controllers.dutching_controller import DutchingController
from telegram_listener import TelegramListener, parse_signal_message


def _sample_dutching_selections() -> List[Dict[str, Any]]:
    return [
        {
            "selectionId": 101,
            "runnerName": "Alpha",
            "price": 2.0,
            "back_ladder": [{"price": 2.0, "size": 120.0}],
            "lay_ladder": [{"price": 2.02, "size": 140.0}],
        },
        {
            "selectionId": 202,
            "runnerName": "Beta",
            "price": 3.0,
            "back_ladder": [{"price": 3.0, "size": 125.0}],
            "lay_ladder": [{"price": 3.05, "size": 130.0}],
        },
    ]


def dutching_controller_semantic_probe_case() -> Dict[str, Any]:
    controller = DutchingController(simulation=True)
    selections = _sample_dutching_selections()
    total_stake = 10.0
    result = controller.preflight_check(
        selections=selections,
        total_stake=total_stake,
        mode="BACK",
    )

    return {
        "status": "ok" if result.is_valid else "error",
        "total_stake": total_stake,
        "book_pct": float(result.details.get("book_pct", 0.0)),
        "errors_count": len(result.errors),
        "warnings_count": len(result.warnings),
        "liquidity_ok": bool(result.liquidity_ok),
        "spread_ok": bool(result.spread_ok),
        "stake_ok": bool(result.stake_ok),
        "price_ok": bool(result.price_ok),
        "book_ok": bool(result.book_ok),
        "legs": {
            "runner_count": len(selections),
            "allocations": [
                {
                    "selectionId": item["selectionId"],
                    "price": item["price"],
                }
                for item in selections
            ],
        },
    }


def dutching_controller_runtime_smoke() -> Dict[str, Any]:
    controller = DutchingController(simulation=True)
    status = controller.get_guardrail_status()
    return {
        "guardrail_type": type(status).__name__,
        "has_value": status is not None,
        "simulation": bool(controller.simulation),
    }


def telegram_listener_semantic_probe_case() -> Dict[str, Any]:
    message = "BACK @2.50 selection_id=101 market_id=1.123456"
    parsed = parse_signal_message(message)

    if parsed is None:
        return {
            "status": "error",
            "action": None,
            "selection_id": None,
            "market_id": None,
            "price": None,
        }

    return {
        "status": "ok",
        "action": parsed.get("action"),
        "selection_id": parsed.get("selection_id"),
        "market_id": parsed.get("market_id"),
        "price": parsed.get("price"),
    }


def telegram_listener_runtime_smoke() -> Dict[str, Any]:
    listener = TelegramListener(api_id=1, api_hash="guardrail")
    listener.set_monitored_chats([123456789])
    listener.set_callbacks(on_signal=lambda *_: None, on_message=lambda *_: None)

    return {
        "running": bool(listener.running),
        "monitored_count": len(listener.monitored_chats),
        "has_signal_callback": listener.signal_callback is not None,
        "has_message_callback": listener.message_callback is not None,
        "default_pattern_count": len(listener.signal_patterns),
    }
