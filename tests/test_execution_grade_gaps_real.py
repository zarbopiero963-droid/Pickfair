import json
import threading
import time

import pytest

from ai.ai_guardrail import AIGuardrail, BlockReason, GuardrailConfig
from core.safety_layer import SafetyLayer
from core.trading_engine import TradingEngine
from database import Database
from pnl_engine import PnLEngine


class DummyBus:
    def __init__(self):
        self.subscribers = {}
        self.events = []

    def subscribe(self, event_name, handler):
        self.subscribers.setdefault(event_name, []).append(handler)

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))
        for handler in self.subscribers.get(event_name, []):
            handler(payload)


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class InstrumentedDB:
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []
        self.saved_cashouts = []
        self.sim_settings = {"virtual_balance": 1000.0}
        self.sim_saved = []
        self.sim_balance_updates = []
        self.reconciled = []
        self.failed = []
        self.raise_on_save_bet = False

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending_sagas.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": json.dumps(payload),
                "status": "PENDING",
                "created_at": time.time(),
            }
        )

    def get_pending_sagas(self):
        return [x for x in self.pending_sagas if x["status"] == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)
        for saga in self.pending_sagas:
            if saga["customer_ref"] == customer_ref:
                saga["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)
        for saga in self.pending_sagas:
            if saga["customer_ref"] == customer_ref:
                saga["status"] = "FAILED"

    def save_bet(
        self,
        event_name,
        market_id,
        market_name,
        bet_type,
        selections,
        total_stake,
        potential_profit,
        status,
    ):
        if self.raise_on_save_bet:
            raise IOError("partial write on save_bet")

        self.saved_bets.append(
            {
                "event_name": event_name,
                "market_id": market_id,
                "market_name": market_name,
                "bet_type": bet_type,
                "selections": selections,
                "total_stake": total_stake,
                "potential_profit": potential_profit,
                "status": status,
            }
        )

    def save_cashout_transaction(self, **kwargs):
        self.saved_cashouts.append(kwargs)

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        self.sim_saved.append(kwargs)

    def increment_simulation_bet_count(self, new_balance):
        self.sim_balance_updates.append(new_balance)
        self.sim_settings["virtual_balance"] = new_balance


class SequencedClient:
    def __init__(self):
        self.place_bet_calls = []
        self.place_orders_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.get_current_orders_calls = []
        self.get_market_book_calls = []

        self.place_bet_side_effects = []
        self.place_orders_side_effects = []
        self.reconcile_orders_response = {
            "currentOrders": [],
            "matched": [],
            "unmatched": [],
        }
        self.market_book = {"runners": []}
        self.place_bet_barrier = None

    def place_bet(
        self,
        market_id,
        selection_id,
        side,
        price,
        size,
        persistence_type="LAPSE",
        customer_ref=None,
    ):
        self.place_bet_calls.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "side": side,
                "price": price,
                "size": size,
                "customer_ref": customer_ref,
            }
        )

        if self.place_bet_barrier is not None:
            self.place_bet_barrier.wait(timeout=1.0)

        if self.place_bet_side_effects:
            effect = self.place_bet_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect

        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET_{selection_id}",
                    "sizeMatched": size,
                }
            ],
        }

    def place_orders(self, market_id, instructions, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
                "customer_ref": customer_ref,
            }
        )

        if self.place_orders_side_effects:
            effect = self.place_orders_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect

        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET_{i['selectionId']}",
                    "sizeMatched": i["limitOrder"]["size"],
                }
                for i in instructions
            ],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": instructions[0]["betId"],
                    "sizeMatched": 0.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        self.get_current_orders_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )
        return self.reconcile_orders_response

    def get_market_book(self, market_id):
        self.get_market_book_calls.append(market_id)
        return self.market_book


@pytest.fixture
def bus():
    return DummyBus()


@pytest.fixture
def executor():
    return DummyExecutor()


@pytest.fixture
def db():
    return InstrumentedDB()


@pytest.fixture
def client():
    return SequencedClient()


@pytest.fixture
def engine(bus, db, client, executor):
    return TradingEngine(bus, db, lambda: client, executor)


def _quick_payload(**overrides):
    payload = {
        "market_id": "1.100",
        "selection_id": 7,
        "bet_type": "BACK",
        "price": 2.5,
        "stake": 10.0,
        "event_name": "Inter - Milan",
        "market_name": "Match Odds",
        "runner_name": "Inter",
        "simulation_mode": False,
    }
    payload.update(overrides)
    return payload


def test_signal_to_submit_fill_persistence_and_recovery_real(
    engine, client, db, bus, monkeypatch
):
    customer_refs = []

    def wrapped_place(*args, **kwargs):
        customer_ref = kwargs.get("customer_ref")
        customer_refs.append(customer_ref)

        client.reconcile_orders_response = {
            "currentOrders": [
                {
                    "customerOrderRef": customer_ref,
                    "customerRef": customer_ref,
                    "marketId": kwargs["market_id"],
                    "sizeMatched": kwargs["size"],
                }
            ],
            "matched": [],
            "unmatched": [],
        }
        raise ConnectionError("submit accepted then socket dropped")

    client.place_bet = wrapped_place
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)

    engine._handle_quick_bet(_quick_payload(stake=6.0))

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["recovered"] is True
    assert success[0][1]["matched"] == pytest.approx(6.0)

    assert db.saved_bets[-1]["status"] == "MATCHED"
    assert len(db.reconciled) == 1
    assert customer_refs[0] == db.reconciled[0]


def test_replay_idempotent_pending_saga_recovery_should_not_duplicate_bet_rows(
    client, executor, monkeypatch
):
    bus = DummyBus()
    db = InstrumentedDB()
    engine = TradingEngine(bus, db, lambda: client, executor)

    ref = "replay-ref-1"
    payload = _quick_payload(stake=4.0)

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": payload["market_id"],
            "selection_id": payload["selection_id"],
            "raw_payload": json.dumps(payload),
            "status": "PENDING",
            "created_at": time.time(),
        }
    )

    client.reconcile_orders_response = {
        "currentOrders": [
            {
                "customerOrderRef": ref,
                "customerRef": ref,
                "marketId": payload["market_id"],
                "sizeMatched": 4.0,
            }
        ],
        "matched": [],
        "unmatched": [],
    }

    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)

    engine._recover_pending_sagas()
    first_len = len(db.saved_bets)

    engine._recover_pending_sagas()
    second_len = len(db.saved_bets)

    assert first_len == 1
    assert second_len == 1


def test_pnl_matches_execution_log_with_matched_and_average_price():
    pnl = PnLEngine(commission=4.5)

    orders = [
        {"side": "BACK", "sizeMatched": 5.0, "averagePriceMatched": 3.0},
        {"side": "BACK", "sizeMatched": 2.0, "averagePriceMatched": 4.0},
    ]

    total = pnl.calculate_selection_pnl(orders, best_back=2.8, best_lay=2.5)
    expected = round(
        pnl.calculate_back_pnl(orders[0], best_lay_price=2.5)
        + pnl.calculate_back_pnl(orders[1], best_lay_price=2.5),
        2,
    )

    assert total == expected
    assert total != 0.0


def test_global_invariant_quick_bet_success_payload_is_safety_valid(engine, bus):
    payload = _quick_payload(stake=5.0)
    engine._handle_quick_bet(payload)

    success = [e[1] for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1

    safety = SafetyLayer()
    assert safety.validate_quick_bet_success(success[0]) is True


def test_retry_windows_guardrail_blocks_after_consecutive_failures():
    guard = AIGuardrail(
        GuardrailConfig(
            consecutive_error_limit=3,
            cooldown_after_error_sec=60.0,
            max_orders_per_minute=99,
            min_tick_count=1,
            min_wom_confidence=0.0,
        )
    )

    guard.record_order("1.1", 1, "BACK", 2.0, success=False)
    guard.record_order("1.1", 1, "BACK", 2.0, success=False)
    guard.record_order("1.1", 1, "BACK", 2.0, success=False)

    result = guard.full_check(
        "MATCH_ODDS",
        tick_count=10,
        wom_confidence=0.9,
        volatility=0.1,
    )

    assert result["can_proceed"] is False
    assert BlockReason.CONSECUTIVE_ERRORS.value in result["reasons"]


def test_safety_kill_switch_blocks_quick_bet_and_no_order_is_sent(
    engine, client, bus
):
    engine._toggle_kill_switch({"enabled": True})
    engine._handle_quick_bet(_quick_payload())

    assert client.place_bet_calls == []

    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert failed[0][1] == "SAFE MODE ATTIVO"


def test_clock_drift_and_cooldown_guardrail_behavior(monkeypatch):
    guard = AIGuardrail(
        GuardrailConfig(
            max_orders_per_minute=1,
            min_tick_count=1,
            min_wom_confidence=0.0,
            consecutive_error_limit=99,
        )
    )

    base = 1000.0
    monkeypatch.setattr(time, "time", lambda: base)
    guard.record_order("1.2", 5, "BACK", 2.0, success=True)

    result_hot = guard.full_check(
        "MATCH_ODDS",
        tick_count=10,
        wom_confidence=0.9,
        volatility=0.1,
    )
    assert result_hot["can_proceed"] is False
    assert BlockReason.OVERTRADE_PROTECTION.value in result_hot["reasons"]

    monkeypatch.setattr(time, "time", lambda: base - 5.0)
    result_drift = guard.full_check(
        "MATCH_ODDS",
        tick_count=10,
        wom_confidence=0.9,
        volatility=0.1,
    )
    assert result_drift["can_proceed"] is False
    assert BlockReason.OVERTRADE_PROTECTION.value in result_drift["reasons"]


def test_out_of_order_recovery_works_with_unmatched_before_current_orders(
    client, executor, monkeypatch
):
    bus = DummyBus()
    db = InstrumentedDB()
    engine = TradingEngine(bus, db, lambda: client, executor)

    ref = "ooo-ref"
    payload = _quick_payload(stake=3.0)

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": payload["market_id"],
            "selection_id": payload["selection_id"],
            "raw_payload": json.dumps(payload),
            "status": "PENDING",
            "created_at": time.time(),
        }
    )

    client.reconcile_orders_response = {
        "currentOrders": [],
        "matched": [],
        "unmatched": [
            {
                "customerOrderRef": ref,
                "customerRef": ref,
                "marketId": payload["market_id"],
                "sizeMatched": 1.5,
            }
        ],
    }

    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)

    engine._recover_pending_sagas()

    assert db.saved_bets[-1]["status"] == "PARTIALLY_MATCHED"
    assert db.pending_sagas[0]["status"] == "RECONCILED"


def test_duplicate_messages_same_payload_should_not_create_two_effects(
    engine, db
):
    payload = _quick_payload(stake=5.0)

    engine._handle_quick_bet(payload)
    engine._handle_quick_bet(payload)

    # Questo è un test di gap: su un engine robusto l'effetto dovrebbe essere uno solo.
    assert len(db.saved_bets) == 1


def test_duplicate_fills_same_recovery_data_should_not_double_count_saved_rows(
    client, executor, monkeypatch
):
    bus = DummyBus()
    db = InstrumentedDB()
    engine = TradingEngine(bus, db, lambda: client, executor)

    ref = "dup-fill-ref"
    payload = _quick_payload(stake=5.0)

    db.pending_sagas.append(
        {
            "customer_ref": ref,
            "market_id": payload["market_id"],
            "selection_id": payload["selection_id"],
            "raw_payload": json.dumps(payload),
            "status": "PENDING",
            "created_at": time.time(),
        }
    )

    client.reconcile_orders_response = {
        "currentOrders": [
            {
                "customerOrderRef": ref,
                "customerRef": ref,
                "marketId": payload["market_id"],
                "sizeMatched": 5.0,
            },
            {
                "customerOrderRef": ref,
                "customerRef": ref,
                "marketId": payload["market_id"],
                "sizeMatched": 5.0,
            },
        ],
        "matched": [],
        "unmatched": [],
    }

    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)

    engine._recover_pending_sagas()

    assert db.saved_bets[-1]["status"] == "MATCHED"
    assert len(db.saved_bets) == 1


def test_cash_exposure_caps_block_low_simulation_balance(engine, bus, db):
    db.sim_settings["virtual_balance"] = 5.0

    engine._handle_quick_bet(
        _quick_payload(
            simulation_mode=True,
            bet_type="LAY",
            price=3.0,
            stake=4.0,
        )
    )

    failed = [e for e in bus.events if e[0] == "QUICK_BET_FAILED"]
    assert len(failed) == 1
    assert "insufficiente" in failed[0][1].lower()
    assert db.sim_saved == []


def test_cancel_fill_concurrency_active_submissions_never_leak(engine, client):
    barrier = threading.Barrier(2)
    client.place_bet_barrier = barrier

    payload = _quick_payload(stake=5.0)

    threads = [
        threading.Thread(target=engine._handle_quick_bet, args=(payload,))
        for _ in range(2)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert engine._active_submissions == set()
    assert len(client.place_bet_calls) == 2


def test_partial_write_db_should_not_mark_reconciled_before_durable_save(
    engine, db
):
    db.raise_on_save_bet = True

    with pytest.raises(OSError, match="partial write on save_bet"):
        engine._handle_quick_bet(_quick_payload(stake=5.0))

    # Questo è un test di gap: la saga non dovrebbe risultare già riconciliata
    # se la persistenza finale fallisce.
    assert db.reconciled == []


def test_payload_corruption_is_rejected_by_safety_layer():
    safety = SafetyLayer()

    with pytest.raises(Exception):
        safety.validate_quick_bet_request(
            {
                "market_id": "1.1",
                "selection_id": "bad",
                "stake": "x",
            }
        )


def test_latency_injection_reconcile_retries_across_failures(
    engine, client, monkeypatch
):
    calls = {"n": 0}

    def flaky_get_current_orders(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("temporary timeout")
        return {
            "currentOrders": [
                {
                    "customerOrderRef": "lat-ref",
                    "customerRef": "lat-ref",
                    "marketId": "1.100",
                    "sizeMatched": 2.0,
                }
            ],
            "matched": [],
            "unmatched": [],
        }

    client.get_current_orders = flaky_get_current_orders
    monkeypatch.setattr(time, "sleep", lambda *_args, **_kwargs: None)

    ok, recovered = engine._reconcile_orders(client, "1.100", "lat-ref")

    assert ok is True
    assert recovered[0]["sizeMatched"] == 2.0


def test_real_database_transaction_rollback_on_duplicate_customer_ref(tmp_path):
    db = Database(db_path=str(tmp_path / "pf.db"))
    payload = {"side": "BACK"}

    db.create_pending_saga("same-ref", "1.1", "7", payload)
    db.create_pending_saga("same-ref", "1.1", "7", payload)

    rows = db.get_pending_sagas()

    assert len(rows) == 1
    assert rows[0]["customer_ref"] == "same-ref"