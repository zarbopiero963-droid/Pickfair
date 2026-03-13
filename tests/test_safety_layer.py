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

    with pytest.raises(PayloadValidationError, match="bet_type: missing"):
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

    with pytest.raises(PayloadValidationError, match="bet_type invalido"):
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

    with pytest.raises(MarketSanityError, match="price <= 1.0"):
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

    with pytest.raises(RiskInvariantError, match="stake <= 0"):
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

    with pytest.raises(PayloadValidationError, match="bet_type: missing"):
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

    with pytest.raises(PayloadValidationError, match="status non ammesso"):
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

    with pytest.raises(PayloadValidationError, match="results vuoto"):
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

    with pytest.raises(MarketSanityError, match="price <= 1"):
        safety.validate_dutching_request(payload)


def test_validate_dutching_success_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.555",
        "bet_type": "BACK",
        "selections": [
            {"selectionId": 1, "runnerName": "Napoli", "price": 2.0, "stake": 10.0},
        ],
        "matched": 10.0,
        "status": "MATCHED",
        "sim": False,
        "total_stake": 10.0,
    }

    assert safety.validate_dutching_success(payload) is True


def test_validate_cashout_request_ok():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.777",
        "selection_id": 7,
        "side": "BACK",
        "stake": 5.0,
        "price": 2.2,
        "green_up": 1.5,
    }

    assert safety.validate_cashout_request(payload) is True


def test_validate_cashout_request_invalid():
    safety = SafetyLayer()

    payload = {
        "market_id": "1.777",
        "selection_id": 7,
        "side": "BACK",
        "stake": 5.0,
        "price": 1.0,
        "green_up": 1.5,
    }

    with pytest.raises(MarketSanityError, match="price <= 1"):
        safety.validate_cashout_request(payload)


def test_validate_cashout_success_ok():
    safety = SafetyLayer()

    payload = {
        "green_up": 1.5,
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
                    "availableToBack": [{"price": 2.0, "size": 100.0}],
                    "availableToLay": [{"price": 2.02, "size": 120.0}],
                },
            }
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
                    "availableToBack": [{"price": 1.0, "size": 100.0}],
                    "availableToLay": [{"price": 2.02, "size": 120.0}],
                },
            }
        ]
    }

    with pytest.raises(MarketSanityError, match="best back <= 1.0"):
        safety.validate_market_book(market_book)


def test_validate_selection_prices_ok():
    safety = SafetyLayer()

    assert safety.validate_selection_prices(2.0, 2.1) is True


def test_validate_selection_prices_lay_lower_than_back():
    safety = SafetyLayer()

    with pytest.raises(MarketSanityError, match="lay < back"):
        safety.validate_selection_prices(2.1, 2.0)


def test_validate_selection_prices_spread_too_wide():
    safety = SafetyLayer()

    with pytest.raises(MarketSanityError, match="spread eccessivo"):
        safety.validate_selection_prices(2.0, 3.0, max_spread_ratio=0.20)


def test_inspect_pending_sagas_reads_db():
    safety = SafetyLayer()
    db = DummyDB()

    db.rows = [
        {
            "customer_ref": "abc",
            "market_id": "1.1",
            "selection_id": "10",
            "status": "PENDING",
            "created_at": time.time() - 120,
            "raw_payload": '{"x": 1}',
        }
    ]

    rows = safety.inspect_pending_sagas(db)

    assert len(rows) == 1
    assert rows[0].customer_ref == "abc"
    assert rows[0].market_id == "1.1"
    assert rows[0].status == "PENDING"
    assert rows[0].age_sec >= 100


def test_get_stale_pending_sagas_filters_old_only():
    safety = SafetyLayer()
    db = DummyDB()

    now = time.time()
    db.rows = [
        {
            "customer_ref": "old",
            "market_id": "1.1",
            "selection_id": "10",
            "status": "PENDING",
            "created_at": now - 120,
        },
        {
            "customer_ref": "fresh",
            "market_id": "1.2",
            "selection_id": "11",
            "status": "PENDING",
            "created_at": now - 5,
        },
        {
            "customer_ref": "done",
            "market_id": "1.3",
            "selection_id": "12",
            "status": "DONE",
            "created_at": now - 999,
        },
    ]

    stale = safety.get_stale_pending_sagas(db, stale_after_sec=60)

    assert len(stale) == 1
    assert stale[0].customer_ref == "old"


def test_watchdog_register_ping_and_status():
    safety = SafetyLayer()
    safety.register_watchdog("engine", timeout_sec=2.0)

    status = safety.get_watchdog_status()

    assert "engine" in status
    assert status["engine"]["enabled"] is True
    assert status["engine"]["triggered"] is False


def test_watchdog_timeout_triggers_callback():
    safety = SafetyLayer()
    triggered = []

    def cb(name, msg):
        triggered.append((name, msg))

    safety.set_watchdog_callback(cb)
    safety.register_watchdog("slow_engine", timeout_sec=0.5)
    safety.start_watchdog(interval_sec=0.1)

    try:
        time.sleep(0.8)
    finally:
        safety.stop_watchdog()

    assert len(triggered) >= 1
    assert triggered[0][0] == "slow_engine"


def test_watchdog_ping_prevents_trigger():
    safety = SafetyLayer()
    triggered = []

    def cb(name, msg):
        triggered.append((name, msg))

    safety.set_watchdog_callback(cb)
    safety.register_watchdog("alive_engine", timeout_sec=0.5)
    safety.start_watchdog(interval_sec=0.1)

    try:
        for _ in range(5):
            safety.watchdog_ping("alive_engine")
            time.sleep(0.1)
    finally:
        safety.stop_watchdog()

    assert triggered == []


def test_safe_validate_helpers_return_tuple():
    safety = SafetyLayer()

    def safe_validate(fn, payload):
        try:
            return True, fn(payload)
        except Exception as e:
            return False, str(e)

    ok, value = safe_validate(
        safety.validate_quick_bet_request,
        {
            "market_id": "1.1",
            "selection_id": 1,
            "bet_type": "BACK",
            "price": 2.0,
            "stake": 5.0,
        },
    )
    bad, error = safe_validate(
        safety.validate_quick_bet_request,
        {
            "market_id": "1.1",
            "selection_id": 1,
            "bet_type": "BACK",
            "price": 1.0,
            "stake": 5.0,
        },
    )

    assert ok is True
    assert value is True
    assert bad is False
    assert "price <= 1.0" in error