import time

import pytest

from core.safety_layer import (
    MarketSanityError,
    PayloadValidationError,
    RiskInvariantError,
    SafetyLayer,
    get_safety_layer,
)


class DummyDB:
    def __init__(self):
        self.rows = []

    def get_pending_sagas(self):
        return list(self.rows)


def test_get_safety_layer_returns_singleton():
    a = get_safety_layer()
    b = get_safety_layer()
    assert a is b
    assert isinstance(a, SafetyLayer)


def test_validate_quick_bet_request_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "event_name": "Juve - Milan",
        "market_name": "Match Odds",
        "runner_name": "Juve",
        "simulation_mode": False,
        "source": "TEST",
    }

    assert safety.validate_quick_bet_request(payload) is True


def test_validate_quick_bet_request_missing_field():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "price": 2.5,
        "stake": 10.0,
    }

    with pytest.raises(PayloadValidationError):
        safety.validate_quick_bet_request(payload)


def test_validate_quick_bet_request_invalid_bet_type():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "HOLD",
        "price": 2.5,
        "stake": 10.0,
    }

    with pytest.raises(PayloadValidationError):
        safety.validate_quick_bet_request(payload)


def test_validate_quick_bet_request_invalid_price():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 1.0,
        "stake": 10.0,
    }

    with pytest.raises(MarketSanityError):
        safety.validate_quick_bet_request(payload)


def test_validate_quick_bet_request_invalid_stake():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.0,
        "stake": 0.0,
    }

    with pytest.raises(RiskInvariantError):
        safety.validate_quick_bet_request(payload)


def test_validate_quick_bet_success_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "matched": 10.0,
        "status": "MATCHED",
        "sim": False,
        "runner_name": "Juve",
        "event_name": "Juve - Milan",
        "market_name": "Match Odds",
        "micro": False,
    }

    assert safety.validate_quick_bet_success(payload) is True


def test_validate_quick_bet_success_missing_bet_type():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "price": 2.5,
        "stake": 10.0,
        "matched": 10.0,
        "status": "MATCHED",
        "sim": False,
    }

    with pytest.raises(PayloadValidationError):
        safety.validate_quick_bet_success(payload)


def test_validate_quick_bet_success_invalid_status():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.234",
        "selection_id": 11,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "matched": 10.0,
        "status": "DONE",
        "sim": False,
    }

    with pytest.raises(PayloadValidationError):
        safety.validate_quick_bet_success(payload)


def test_validate_dutching_request_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.555",
        "market_type": "MATCH_ODDS",
        "event_name": "Napoli - Roma",
        "market_name": "Match Odds",
        "bet_type": "BACK",
        "total_stake": 20.0,
        "results": [
            {"selectionId": 1, "runnerName": "Napoli", "price": 2.0, "stake": 10.0},
            {"selectionId": 2, "runnerName": "Roma", "price": 3.0, "stake": 10.0},
        ],
        "simulation_mode": False,
    }

    assert safety.validate_dutching_request(payload) is True


def test_validate_dutching_request_empty_results():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.555",
        "bet_type": "BACK",
        "total_stake": 20.0,
        "results": [],
    }

    with pytest.raises(PayloadValidationError):
        safety.validate_dutching_request(payload)


def test_validate_dutching_request_bad_runner_price():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.555",
        "bet_type": "BACK",
        "total_stake": 20.0,
        "results": [
            {"selectionId": 1, "runnerName": "Napoli", "price": 1.0, "stake": 10.0},
        ],
    }

    with pytest.raises(MarketSanityError):
        safety.validate_dutching_request(payload)


def test_validate_dutching_success_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.555",
        "bet_type": "BACK",
        "selections": [
            {"selectionId": 1, "runnerName": "Napoli", "price": 2.0, "stake": 10.0},
            {"selectionId": 2, "runnerName": "Roma", "price": 3.0, "stake": 10.0},
        ],
        "matched": 20.0,
        "status": "MATCHED",
        "sim": False,
        "total_stake": 20.0,
    }

    assert safety.validate_dutching_success(payload) is True


def test_validate_cashout_request_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.777",
        "selection_id": 55,
        "side": "LAY",
        "stake": 5.0,
        "price": 1.80,
        "green_up": 2.50,
    }

    assert safety.validate_cashout_request(payload) is True


def test_validate_cashout_request_invalid():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.777",
        "selection_id": 55,
        "side": "LAY",
        "stake": -1.0,
        "price": 1.80,
        "green_up": 2.50,
    }

    with pytest.raises(RiskInvariantError):
        safety.validate_cashout_request(payload)


def test_validate_cashout_success_ok():
    safety = SafetyLayer()

    payload = {
        "green_up": 2.5,
        "matched": 5.0,
        "status": "MATCHED",
        "micro": False,
    }

    assert safety.validate_cashout_success(payload) is True


def test_validate_market_book_ok():
    safety = SafetyLayer()

    market_book = {
        "runners": [
            {
                "selectionId": 1,
                "ex": {
                    "availableToBack": [{"price": 2.0, "size": 100}],
                    "availableToLay": [{"price": 2.02, "size": 100}],
                },
            },
            {
                "selectionId": 2,
                "ex": {
                    "availableToBack": [{"price": 3.0, "size": 100}],
                    "availableToLay": [{"price": 3.05, "size": 100}],
                },
            },
        ]
    }

    assert safety.validate_market_book(market_book) is True


def test_validate_market_book_invalid():
    safety = SafetyLayer()

    market_book = {
        "runners": [
            {
                "selectionId": 1,
                "ex": {
                    "availableToBack": [{"price": 1.0, "size": 100}],
                    "availableToLay": [{"price": 2.02, "size": 100}],
                },
            }
        ]
    }

    with pytest.raises(MarketSanityError):
        safety.validate_market_book(market_book)


def test_validate_selection_prices_ok():
    safety = SafetyLayer()
    assert safety.validate_selection_prices(2.0, 2.04) is True


def test_validate_selection_prices_lay_lower_than_back():
    safety = SafetyLayer()
    with pytest.raises(MarketSanityError):
        safety.validate_selection_prices(2.0, 1.99)


def test_validate_selection_prices_spread_too_wide():
    safety = SafetyLayer()
    with pytest.raises(MarketSanityError):
        safety.validate_selection_prices(2.0, 3.0, max_spread_ratio=0.20)


def test_inspect_pending_sagas_reads_db():
    safety = SafetyLayer()
    db = DummyDB()
    db.rows = [
        {
            "customer_ref": "abc123",
            "market_id": "1.111",
            "selection_id": "10",
            "status": "PENDING",
            "created_at": str(time.time() - 120),
            "raw_payload": '{"x":1}',
        }
    ]

    rows = safety.inspect_pending_sagas(db, stale_after_sec=60.0)

    assert len(rows) == 1
    assert rows[0].customer_ref == "abc123"
    assert rows[0].market_id == "1.111"
    assert rows[0].status == "PENDING"
    assert rows[0].age_sec >= 100


def test_get_stale_pending_sagas_filters_old_only():
    safety = SafetyLayer()
    db = DummyDB()
    now = time.time()
    db.rows = [
        {
            "customer_ref": "old_saga",
            "market_id": "1.111",
            "selection_id": "10",
            "status": "PENDING",
            "created_at": str(now - 120),
            "raw_payload": "{}",
        },
        {
            "customer_ref": "fresh_saga",
            "market_id": "1.222",
            "selection_id": "20",
            "status": "PENDING",
            "created_at": str(now - 5),
            "raw_payload": "{}",
        },
        {
            "customer_ref": "done_saga",
            "market_id": "1.333",
            "selection_id": "30",
            "status": "RECONCILED",
            "created_at": str(now - 300),
            "raw_payload": "{}",
        },
    ]

    stale = safety.get_stale_pending_sagas(db, stale_after_sec=60.0)

    assert len(stale) == 1
    assert stale[0].customer_ref == "old_saga"


def test_watchdog_register_ping_and_status():
    safety = SafetyLayer()
    safety.register_watchdog("trading_engine", timeout_sec=1.0)

    status = safety.get_watchdog_status()
    assert "trading_engine" in status
    assert status["trading_engine"]["enabled"] is True

    time.sleep(0.05)
    safety.watchdog_ping("trading_engine")

    status2 = safety.get_watchdog_status()
    assert status2["trading_engine"]["last_ping_age_sec"] >= 0.0


def test_watchdog_timeout_triggers_callback():
    safety = SafetyLayer()
    triggered = []

    def cb(name, error):
        triggered.append((name, error))

    safety.set_watchdog_callback(cb)
    safety.register_watchdog("engine_x", timeout_sec=0.2)
    safety.start_watchdog(interval_sec=0.05)

    try:
        time.sleep(0.35)
    finally:
        safety.stop_watchdog()

    assert len(triggered) >= 1
    assert triggered[0][0] == "engine_x"
    assert "Watchdog timeout" in triggered[0][1]


def test_watchdog_ping_prevents_trigger():
    safety = SafetyLayer()
    triggered = []

    def cb(name, error):
        triggered.append((name, error))

    safety.set_watchdog_callback(cb)
    safety.register_watchdog("engine_ok", timeout_sec=0.25)
    safety.start_watchdog(interval_sec=0.05)

    try:
        for _ in range(5):
            safety.watchdog_ping("engine_ok")
            time.sleep(0.08)
    finally:
        safety.stop_watchdog()

    assert triggered == []


def test_safe_validate_helpers_return_tuple():
    safety = SafetyLayer()

    ok, err = safety.safe_validate_quick_bet_request(
        {
            "market_id": "1.999",
            "selection_id": 44,
            "bet_type": "LAY",
            "price": 2.2,
            "stake": 5.0,
        }
    )
    assert ok is True
    assert err is None

    ok2, err2 = safety.safe_validate_quick_bet_request(
        {
            "market_id": "1.999",
            "selection_id": 44,
            "price": 2.2,
            "stake": 5.0,
        }
    )
    assert ok2 is False
    assert isinstance(err2, str)
    assert err2