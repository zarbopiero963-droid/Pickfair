import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pytest


@dataclass
class Order:
    order_id: str
    market_id: str
    selection_id: int
    side: str
    price: float
    size: float
    filled: float = 0.0
    status: str = "OPEN"  # OPEN / FILLED / CANCELED / REJECTED
    version: int = 0


@dataclass
class FillEvent:
    event_id: str
    order_id: str
    size: float
    price: float


@dataclass
class AckEvent:
    event_id: str
    order_id: str


@dataclass
class CancelEvent:
    event_id: str
    order_id: str


@dataclass
class AmendEvent:
    event_id: str
    order_id: str
    new_price: Optional[float] = None
    new_size: Optional[float] = None


@dataclass
class EngineConfig:
    max_stake: float = 50.0
    max_exposure: float = 120.0
    cooldown_seconds: float = 0.0
    retry_limit: int = 2
    ack_timeout_seconds: float = 0.5
    allowed_markets: Tuple[str, ...] = ("MATCH_ODDS",)
    fail_closed: bool = True


@dataclass
class LedgerState:
    orders: Dict[str, Order] = field(default_factory=dict)
    processed_event_ids: set = field(default_factory=set)
    processed_persistence_ids: set = field(default_factory=set)
    pnl_realized: float = 0.0
    exposure: float = 0.0
    position_by_selection: Dict[int, float] = field(default_factory=dict)
    audit_log: List[dict] = field(default_factory=list)
    safe_mode: bool = False
    last_submit_ts: float = 0.0


class FakePersistence:
    def __init__(self):
        self.rows = []
        self.fail_next_write = False
        self.partial_write_mode = False
        self.lock = threading.Lock()

    def append_once(self, op_id: str, row: dict):
        with self.lock:
            if self.fail_next_write:
                self.fail_next_write = False
                raise IOError("simulated persistence failure")

            if self.partial_write_mode:
                partial = dict(row)
                partial["partial"] = True
                self.rows.append((op_id, partial))
                raise IOError("simulated partial write")

            if any(existing_op_id == op_id for existing_op_id, _ in self.rows):
                return False

            self.rows.append((op_id, copy.deepcopy(row)))
            return True

    def snapshot(self):
        return copy.deepcopy(self.rows)


class FakeBroker:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.submit_calls = 0
        self.cancel_calls = 0
        self.amend_calls = 0
        self.fail_submit_times = 0
        self.disconnect_mid_submit = False
        self.network_flap = False
        self.latency_seconds = 0.0
        self.outbox: List[object] = []
        self.lock = threading.Lock()

    def submit(self, order: Order):
        with self.lock:
            self.submit_calls += 1
            if self.latency_seconds:
                time.sleep(self.latency_seconds)
            if self.network_flap:
                raise ConnectionError("network flap")
            if self.disconnect_mid_submit:
                self.disconnect_mid_submit = False
                self.orders[order.order_id] = copy.deepcopy(order)
                raise ConnectionError("disconnect after broker accepted order")
            if self.fail_submit_times > 0:
                self.fail_submit_times -= 1
                raise ConnectionError("submit failed")

            self.orders[order.order_id] = copy.deepcopy(order)
            self.outbox.append(AckEvent(event_id=f"ack-{order.order_id}", order_id=order.order_id))
            return True

    def cancel(self, order_id: str):
        with self.lock:
            self.cancel_calls += 1
            order = self.orders[order_id]
            if order.status == "FILLED":
                return False
            order.status = "CANCELED"
            self.outbox.append(CancelEvent(event_id=f"cancel-{order_id}", order_id=order_id))
            return True

    def amend(self, order_id: str, new_price=None, new_size=None):
        with self.lock:
            self.amend_calls += 1
            order = self.orders[order_id]
            if order.status != "OPEN":
                return False
            if new_price is not None:
                order.price = new_price
            if new_size is not None:
                if new_size < order.filled:
                    raise ValueError("cannot amend below filled size")
                order.size = new_size
            order.version += 1
            self.outbox.append(
                AmendEvent(
                    event_id=f"amend-{order_id}-{order.version}",
                    order_id=order_id,
                    new_price=new_price,
                    new_size=new_size,
                )
            )
            return True

    def emit_fill(self, order_id: str, size: float, price: Optional[float] = None, event_id: Optional[str] = None):
        with self.lock:
            order = self.orders[order_id]
            px = price if price is not None else order.price
            if event_id is None:
                event_id = f"fill-{order_id}-{len(self.outbox)}"
            self.outbox.append(FillEvent(event_id=event_id, order_id=order_id, size=size, price=px))

    def drain_events(self):
        with self.lock:
            events = list(self.outbox)
            self.outbox.clear()
            return events


class ReferenceEngine:
    def __init__(self, broker: FakeBroker, persistence: FakePersistence, config: Optional[EngineConfig] = None):
        self.broker = broker
        self.persistence = persistence
        self.config = config or EngineConfig()
        self.state = LedgerState()
        self._seq = 0
        self._lock = threading.RLock()

    def _next_id(self, prefix: str):
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def _now(self):
        return time.monotonic()

    def _persist_once(self, op_id: str, row: dict):
        if op_id in self.state.processed_persistence_ids:
            return False
        stored = self.persistence.append_once(op_id, row)
        if stored:
            self.state.processed_persistence_ids.add(op_id)
        return stored

    def set_safe_mode(self, enabled: bool):
        self.state.safe_mode = enabled

    def reconcile_from_broker(self):
        with self._lock:
            for order_id, broker_order in self.broker.orders.items():
                existing = self.state.orders.get(order_id)
                if existing is None:
                    self.state.orders[order_id] = copy.deepcopy(broker_order)
                else:
                    existing.price = broker_order.price
                    existing.size = broker_order.size
                    existing.status = broker_order.status
                    existing.version = broker_order.version

    def recover_from_persistence(self):
        with self._lock:
            new_state = LedgerState(safe_mode=self.state.safe_mode)
            for op_id, row in self.persistence.snapshot():
                if row.get("partial"):
                    continue
                kind = row["kind"]
                if kind == "submit":
                    order = Order(**row["order"])
                    new_state.orders[order.order_id] = order
                elif kind == "fill":
                    if row["event_id"] in new_state.processed_event_ids:
                        continue
                    new_state.processed_event_ids.add(row["event_id"])
                    self._apply_fill_to_state(new_state, FillEvent(**row["payload"]))
                elif kind == "cancel":
                    oid = row["order_id"]
                    if oid in new_state.orders:
                        new_state.orders[oid].status = "CANCELED"
                elif kind == "amend":
                    oid = row["order_id"]
                    if oid in new_state.orders:
                        order = new_state.orders[oid]
                        if row["new_price"] is not None:
                            order.price = row["new_price"]
                        if row["new_size"] is not None:
                            order.size = row["new_size"]
            self.state = new_state
            self._recompute_exposure()

    def _apply_fill_to_state(self, state: LedgerState, fill: FillEvent):
        order = state.orders[fill.order_id]
        remaining = order.size - order.filled
        applied = min(fill.size, remaining)
        if applied <= 0:
            return

        order.filled += applied
        if order.filled >= order.size:
            order.status = "FILLED"

        signed = applied if order.side == "BACK" else -applied
        state.position_by_selection[order.selection_id] = state.position_by_selection.get(order.selection_id, 0.0) + signed
        state.exposure = sum(
            max(0.0, o.size - o.filled) for o in state.orders.values() if o.status == "OPEN"
        )
        state.pnl_realized += applied * (fill.price - 1.0) if order.side == "BACK" else applied * (1.0 - fill.price)

    def _recompute_exposure(self):
        self.state.exposure = sum(
            max(0.0, o.size - o.filled) for o in self.state.orders.values() if o.status == "OPEN"
        )

    def submit_signal(
        self,
        market_type: str,
        market_id: str,
        selection_id: int,
        side: str,
        price: float,
        suggested_size: float,
        risk_ok: bool = True,
        clock: Optional[float] = None,
    ) -> str:
        with self._lock:
            now = clock if clock is not None else self._now()

            if self.state.safe_mode and self.config.fail_closed:
                raise RuntimeError("safe mode active")

            if market_type not in self.config.allowed_markets:
                raise RuntimeError("market not allowed")

            if not risk_ok:
                raise RuntimeError("risk rejected")

            if now - self.state.last_submit_ts < self.config.cooldown_seconds:
                raise RuntimeError("cooldown active")

            size = min(float(suggested_size), self.config.max_stake)
            projected_exposure = self.state.exposure + size
            if projected_exposure > self.config.max_exposure:
                raise RuntimeError("max exposure exceeded")

            order_id = self._next_id("ord")
            order = Order(
                order_id=order_id,
                market_id=market_id,
                selection_id=selection_id,
                side=side,
                price=price,
                size=size,
            )

            retries = 0
            while True:
                try:
                    self.broker.submit(order)
                    break
                except ConnectionError:
                    retries += 1
                    if retries > self.config.retry_limit:
                        raise

            self.state.orders[order_id] = copy.deepcopy(order)
            self.state.last_submit_ts = now
            self._recompute_exposure()
            self._persist_once(
                f"submit:{order_id}",
                {"kind": "submit", "order": copy.deepcopy(order).__dict__},
            )
            return order_id

    def process_event(self, event):
        with self._lock:
            if getattr(event, "event_id", None) in self.state.processed_event_ids:
                return False

            if isinstance(event, AckEvent):
                self.state.processed_event_ids.add(event.event_id)
                return True

            if isinstance(event, FillEvent):
                if event.order_id not in self.state.orders:
                    return False
                self.state.processed_event_ids.add(event.event_id)
                self._apply_fill_to_state(self.state, event)
                self._persist_once(
                    f"fill:{event.event_id}",
                    {"kind": "fill", "event_id": event.event_id, "payload": event.__dict__},
                )
                return True

            if isinstance(event, CancelEvent):
                if event.order_id not in self.state.orders:
                    return False
                self.state.processed_event_ids.add(event.event_id)
                self.state.orders[event.order_id].status = "CANCELED"
                self._recompute_exposure()
                self._persist_once(
                    f"cancel:{event.order_id}",
                    {"kind": "cancel", "order_id": event.order_id},
                )
                return True

            if isinstance(event, AmendEvent):
                if event.order_id not in self.state.orders:
                    return False
                self.state.processed_event_ids.add(event.event_id)
                order = self.state.orders[event.order_id]
                if event.new_price is not None:
                    order.price = event.new_price
                if event.new_size is not None:
                    order.size = event.new_size
                self._recompute_exposure()
                self._persist_once(
                    f"amend:{event.order_id}:{event.event_id}",
                    {
                        "kind": "amend",
                        "order_id": event.order_id,
                        "new_price": event.new_price,
                        "new_size": event.new_size,
                    },
                )
                return True

            return False

    def process_broker_outbox(self):
        for event in self.broker.drain_events():
            self.process_event(event)

    def cancel_order(self, order_id: str):
        with self._lock:
            self.broker.cancel(order_id)
            self.process_broker_outbox()

    def amend_order(self, order_id: str, new_price=None, new_size=None):
        with self._lock:
            self.broker.amend(order_id, new_price=new_price, new_size=new_size)
            self.process_broker_outbox()

    def snapshot(self):
        return copy.deepcopy(self.state)


@pytest.fixture
def broker():
    return FakeBroker()


@pytest.fixture
def persistence():
    return FakePersistence()


@pytest.fixture
def engine(broker, persistence):
    return ReferenceEngine(
        broker=broker,
        persistence=persistence,
        config=EngineConfig(
            max_stake=50.0,
            max_exposure=120.0,
            cooldown_seconds=0.2,
            retry_limit=2,
            ack_timeout_seconds=0.2,
            allowed_markets=("MATCH_ODDS",),
            fail_closed=True,
        ),
    )


def test_signal_to_risk_to_sizing_to_submit_to_ack_to_fill_to_pnl_to_persist_to_recovery(engine, broker, persistence):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.100",
        selection_id=11,
        side="BACK",
        price=2.10,
        suggested_size=70.0,
        risk_ok=True,
        clock=10.0,
    )

    assert order_id in engine.state.orders
    assert engine.state.orders[order_id].size == 50.0

    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=20.0, price=2.10, event_id="fill-1")
    broker.emit_fill(order_id, size=30.0, price=2.10, event_id="fill-2")
    engine.process_broker_outbox()

    order = engine.state.orders[order_id]
    assert order.filled == 50.0
    assert order.status == "FILLED"
    assert engine.state.exposure == 0.0
    assert engine.state.pnl_realized == pytest.approx(55.0)

    recovered = ReferenceEngine(broker, persistence, engine.config)
    recovered.recover_from_persistence()
    assert recovered.state.orders[order_id].filled == 50.0
    assert recovered.state.orders[order_id].status == "FILLED"
    assert recovered.state.pnl_realized == pytest.approx(55.0)


def test_retry_window_recovers_transient_submit_failures(engine, broker):
    broker.fail_submit_times = 2
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.200",
        selection_id=5,
        side="BACK",
        price=1.80,
        suggested_size=10.0,
        risk_ok=True,
        clock=20.0,
    )
    assert order_id in engine.state.orders
    assert broker.submit_calls == 3


def test_submit_fails_after_retry_budget_exhausted(engine, broker):
    broker.fail_submit_times = 3
    with pytest.raises(ConnectionError):
        engine.submit_signal(
            market_type="MATCH_ODDS",
            market_id="1.201",
            selection_id=5,
            side="BACK",
            price=1.80,
            suggested_size=10.0,
            risk_ok=True,
            clock=20.0,
        )


def test_reconcile_prevents_ghost_order_after_disconnect_mid_submit(engine, broker):
    broker.disconnect_mid_submit = True

    with pytest.raises(ConnectionError):
        engine.submit_signal(
            market_type="MATCH_ODDS",
            market_id="1.300",
            selection_id=9,
            side="BACK",
            price=2.00,
            suggested_size=10.0,
            risk_ok=True,
            clock=30.0,
        )

    assert len(engine.state.orders) == 0
    assert len(broker.orders) == 1

    engine.reconcile_from_broker()
    assert len(engine.state.orders) == 1
    order = next(iter(engine.state.orders.values()))
    assert order.market_id == "1.300"
    assert order.status == "OPEN"


def test_duplicate_fill_event_is_idempotent(engine, broker):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.400",
        selection_id=1,
        side="BACK",
        price=2.50,
        suggested_size=10.0,
        risk_ok=True,
        clock=40.0,
    )
    engine.process_broker_outbox()

    broker.emit_fill(order_id, size=5.0, price=2.50, event_id="dup-fill-1")
    broker.emit_fill(order_id, size=5.0, price=2.50, event_id="dup-fill-1")
    engine.process_broker_outbox()

    assert engine.state.orders[order_id].filled == 5.0
    assert engine.state.pnl_realized == pytest.approx(7.5)


def test_replay_same_persistence_log_produces_same_final_state(engine, broker, persistence):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.401",
        selection_id=1,
        side="BACK",
        price=2.00,
        suggested_size=12.0,
        risk_ok=True,
        clock=40.0,
    )
    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=12.0, price=2.00, event_id="fill-r1")
    engine.process_broker_outbox()

    r1 = ReferenceEngine(broker, persistence, engine.config)
    r2 = ReferenceEngine(broker, persistence, engine.config)
    r1.recover_from_persistence()
    r2.recover_from_persistence()

    assert r1.state.orders.keys() == r2.state.orders.keys()
    assert r1.state.orders[order_id].filled == r2.state.orders[order_id].filled
    assert r1.state.pnl_realized == r2.state.pnl_realized
    assert r1.state.position_by_selection == r2.state.position_by_selection


def test_partial_fill_then_amend_then_cancel_then_late_duplicate_fill_does_not_break_ledger(engine, broker):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.500",
        selection_id=3,
        side="BACK",
        price=2.20,
        suggested_size=40.0,
        risk_ok=True,
        clock=50.0,
    )
    engine.process_broker_outbox()

    broker.emit_fill(order_id, size=10.0, price=2.20, event_id="pf-1")
    engine.process_broker_outbox()
    assert engine.state.orders[order_id].filled == 10.0
    assert engine.state.exposure == 30.0

    engine.amend_order(order_id, new_price=2.30, new_size=25.0)
    assert engine.state.orders[order_id].price == 2.30
    assert engine.state.orders[order_id].size == 25.0
    assert engine.state.exposure == 15.0

    engine.cancel_order(order_id)
    assert engine.state.orders[order_id].status == "CANCELED"
    assert engine.state.exposure == 0.0

    broker.emit_fill(order_id, size=5.0, price=2.30, event_id="late-1")
    broker.emit_fill(order_id, size=5.0, price=2.30, event_id="late-1")
    engine.process_broker_outbox()

    assert engine.state.orders[order_id].filled == 15.0
    assert engine.state.position_by_selection[3] == pytest.approx(15.0)


def test_net_position_correct_after_crash_restart(engine, broker, persistence):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.600",
        selection_id=88,
        side="BACK",
        price=1.90,
        suggested_size=20.0,
        risk_ok=True,
        clock=60.0,
    )
    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=7.0, price=1.90, event_id="crash-fill-1")
    engine.process_broker_outbox()

    restarted = ReferenceEngine(broker, persistence, engine.config)
    restarted.recover_from_persistence()

    assert restarted.state.orders[order_id].filled == 7.0
    assert restarted.state.position_by_selection[88] == pytest.approx(7.0)
    assert restarted.state.exposure == pytest.approx(13.0)
    assert restarted.state.pnl_realized == pytest.approx(6.3)


def test_pnl_matches_execution_log(engine, broker):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.601",
        selection_id=90,
        side="BACK",
        price=3.00,
        suggested_size=10.0,
        risk_ok=True,
        clock=61.0,
    )
    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=4.0, price=3.00, event_id="pnl-1")
    broker.emit_fill(order_id, size=6.0, price=3.00, event_id="pnl-2")
    engine.process_broker_outbox()

    expected = 4.0 * (3.00 - 1.0) + 6.0 * (3.00 - 1.0)
    assert engine.state.pnl_realized == pytest.approx(expected)


def test_cooldown_enforced_with_consistent_clock(engine):
    engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.700",
        selection_id=1,
        side="BACK",
        price=2.0,
        suggested_size=10.0,
        risk_ok=True,
        clock=100.0,
    )

    with pytest.raises(RuntimeError, match="cooldown"):
        engine.submit_signal(
            market_type="MATCH_ODDS",
            market_id="1.701",
            selection_id=1,
            side="BACK",
            price=2.0,
            suggested_size=10.0,
            risk_ok=True,
            clock=100.1,
        )

    oid = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.702",
        selection_id=1,
        side="BACK",
        price=2.0,
        suggested_size=10.0,
        risk_ok=True,
        clock=100.3,
    )
    assert oid in engine.state.orders


def test_clock_drift_backward_does_not_bypass_guardrails(engine):
    engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.703",
        selection_id=1,
        side="BACK",
        price=2.0,
        suggested_size=10.0,
        risk_ok=True,
        clock=200.0,
    )

    with pytest.raises(RuntimeError):
        engine.submit_signal(
            market_type="MATCH_ODDS",
            market_id="1.704",
            selection_id=1,
            side="BACK",
            price=2.0,
            suggested_size=10.0,
            risk_ok=True,
            clock=199.5,
        )


def test_out_of_order_fill_before_ack_is_still_consistent(engine, broker):
    order_id = engine.submit_signal(
        market_type="MATCH_ODDS",
        market_id="1.800",
        selection_id=55,
        side="BACK",
        price=2.40,
        suggested_size=10.0,
        risk_ok=True,
        clock=80.0,
    )

    broker.drain_events()
    broker.emit_fill(order_id, size=10.0, price=2.40, event_id="ooo-fill")
    broker.outbox.append(AckEvent(event_id="ooo-ack", order_id=order_id))
    engine.process_broker_outbox()

    assert engine.state.orders[order_id].status == "FILLED"
    assert engine.state.orders[order_id].filled == 10.0


def test_equivalent_event_sequences_produce_same_final_state():
    cfg = EngineConfig(cooldown_seconds=0.0)

    broker1 = FakeBroker()
    e1 = ReferenceEngine(broker1, FakePersistence(), cfg)
    oid1 = e1.submit_signal("MATCH_ODDS", "1.801", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    e1.process_broker_outbox()
    broker1.emit_fill(oid1, size=5.0, price=2.0, event_id="eq-fill-1")
    broker1.emit_fill(oid1, size=5.0, price=2.0, event_id="eq-fill-2")
    e1.process_broker_outbox()

    broker2 = FakeBroker()
    e2 = ReferenceEngine(broker2, FakePersistence(), cfg)
    oid2 = e2.submit_signal("MATCH_ODDS", "1.801", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    e2.process_broker_outbox()
    broker2.emit_fill(oid2, size=10.0, price=2.0, event_id="eq-fill-merged")
    e2.process_broker_outbox()

    s1 = e1.snapshot()
    s2 = e2.snapshot()

    assert s1.orders[oid1].filled == s2.orders[oid2].filled
    assert s1.pnl_realized == s2.pnl_realized
    assert s1.position_by_selection == s2.position_by_selection
    assert s1.exposure == s2.exposure == 0.0


def test_global_invariant_exposure_never_negative(engine, broker):
    order_id = engine.submit_signal(
        "MATCH_ODDS", "1.900", 1, "BACK", 2.0, 10.0, True, clock=1.0
    )
    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=7.0, price=2.0, event_id="inv-fill-1")
    broker.emit_fill(order_id, size=7.0, price=2.0, event_id="inv-fill-2")
    engine.process_broker_outbox()

    assert engine.state.exposure >= 0.0
    assert engine.state.orders[order_id].filled == 10.0
    assert engine.state.exposure == 0.0


def test_global_invariant_liability_never_above_limit(engine):
    engine.submit_signal("MATCH_ODDS", "1.901", 1, "BACK", 2.0, 50.0, True, clock=1.0)
    engine.process_broker_outbox()
    engine.submit_signal("MATCH_ODDS", "1.902", 1, "BACK", 2.0, 50.0, True, clock=1.3)
    engine.process_broker_outbox()

    with pytest.raises(RuntimeError, match="max exposure"):
        engine.submit_signal("MATCH_ODDS", "1.903", 1, "BACK", 2.0, 30.0, True, clock=1.6)


def test_recovered_state_equals_rebuilt_state_from_log(engine, broker, persistence):
    order_id = engine.submit_signal("MATCH_ODDS", "1.904", 77, "BACK", 2.5, 20.0, True, clock=1.0)
    engine.process_broker_outbox()
    broker.emit_fill(order_id, size=8.0, price=2.5, event_id="rec-1")
    engine.process_broker_outbox()
    engine.amend_order(order_id, new_price=2.6, new_size=20.0)

    recovered = ReferenceEngine(broker, persistence, engine.config)
    recovered.recover_from_persistence()

    live = engine.snapshot()
    rebuilt = recovered.snapshot()

    assert rebuilt.orders[order_id].filled == live.orders[order_id].filled
    assert rebuilt.orders[order_id].price == live.orders[order_id].price
    assert rebuilt.position_by_selection == live.position_by_selection
    assert rebuilt.pnl_realized == live.pnl_realized


def test_cancel_and_fill_concurrent_do_not_corrupt_ledger(engine, broker):
    order_id = engine.submit_signal("MATCH_ODDS", "1.905", 66, "BACK", 2.0, 20.0, True, clock=1.0)
    engine.process_broker_outbox()

    errors = []

    def do_cancel():
        try:
            engine.cancel_order(order_id)
        except Exception as e:
            errors.append(e)

    def do_fill():
        try:
            broker.emit_fill(order_id, size=10.0, price=2.0, event_id="conc-fill")
            engine.process_broker_outbox()
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=do_cancel)
    t2 = threading.Thread(target=do_fill)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    order = engine.state.orders[order_id]
    assert order.filled in (0.0, 10.0)
    assert order.status in ("CANCELED", "FILLED", "OPEN")
    assert engine.state.exposure >= 0.0


def test_fault_injection_network_flap(engine, broker):
    broker.network_flap = True
    with pytest.raises(ConnectionError):
        engine.submit_signal("MATCH_ODDS", "2.000", 1, "BACK", 2.0, 10.0, True, clock=1.0)


def test_fault_injection_partial_write_does_not_duplicate_on_retry(broker, persistence):
    engine = ReferenceEngine(broker, persistence, EngineConfig(cooldown_seconds=0.0))
    order_id = engine.submit_signal("MATCH_ODDS", "2.001", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    engine.process_broker_outbox()

    persistence.partial_write_mode = True
    broker.emit_fill(order_id, size=5.0, price=2.0, event_id="pw-1")
    with pytest.raises(IOError):
        engine.process_broker_outbox()

    persistence.partial_write_mode = False
    engine.process_event(FillEvent(event_id="pw-1", order_id=order_id, size=5.0, price=2.0))

    good_rows = [row for _, row in persistence.rows if row.get("kind") == "fill" and not row.get("partial")]
    assert len(good_rows) <= 1
    assert engine.state.orders[order_id].filled == 5.0


def test_fault_injection_payload_corruption_is_rejected(engine):
    result = engine.process_event({"bad": "payload"})
    assert result is False


def test_fault_injection_duplicate_event_ids_are_ignored(engine, broker):
    order_id = engine.submit_signal("MATCH_ODDS", "2.002", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    engine.process_broker_outbox()

    evt = FillEvent(event_id="dup-evt", order_id=order_id, size=4.0, price=2.0)
    assert engine.process_event(evt) is True
    assert engine.process_event(evt) is False
    assert engine.state.orders[order_id].filled == 4.0


def test_fault_injection_broker_latency_does_not_break_consistency(engine, broker):
    broker.latency_seconds = 0.01
    order_id = engine.submit_signal("MATCH_ODDS", "2.003", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    assert order_id in engine.state.orders


def test_max_stake_is_hard_enforced(engine):
    order_id = engine.submit_signal("MATCH_ODDS", "2.100", 1, "BACK", 2.0, 999.0, True, clock=1.0)
    assert engine.state.orders[order_id].size == 50.0


def test_max_exposure_is_hard_enforced(engine):
    engine.submit_signal("MATCH_ODDS", "2.101", 1, "BACK", 2.0, 50.0, True, clock=1.0)
    engine.process_broker_outbox()
    engine.submit_signal("MATCH_ODDS", "2.102", 1, "BACK", 2.0, 50.0, True, clock=1.3)
    engine.process_broker_outbox()

    with pytest.raises(RuntimeError, match="max exposure"):
        engine.submit_signal("MATCH_ODDS", "2.103", 1, "BACK", 2.0, 21.0, True, clock=1.6)


def test_throttle_and_cooldown_are_hard_enforced(engine):
    engine.submit_signal("MATCH_ODDS", "2.104", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    with pytest.raises(RuntimeError, match="cooldown"):
        engine.submit_signal("MATCH_ODDS", "2.105", 1, "BACK", 2.0, 10.0, True, clock=1.01)


def test_block_unallowed_markets(engine):
    with pytest.raises(RuntimeError, match="market not allowed"):
        engine.submit_signal("OVER_UNDER", "2.106", 1, "BACK", 2.0, 10.0, True, clock=1.0)


def test_block_incoherent_state_fail_closed(engine):
    engine.set_safe_mode(True)
    with pytest.raises(RuntimeError, match="safe mode"):
        engine.submit_signal("MATCH_ODDS", "2.107", 1, "BACK", 2.0, 10.0, True, clock=1.0)


def test_no_order_in_safe_mode_never(engine, broker):
    engine.set_safe_mode(True)
    with pytest.raises(RuntimeError):
        engine.submit_signal("MATCH_ODDS", "2.108", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    assert broker.submit_calls == 0
    assert len(engine.state.orders) == 0


def test_risk_rejection_is_fail_closed(engine, broker):
    with pytest.raises(RuntimeError, match="risk rejected"):
        engine.submit_signal("MATCH_ODDS", "2.109", 1, "BACK", 2.0, 10.0, False, clock=1.0)
    assert broker.submit_calls == 0


def test_persisted_operations_are_idempotent(engine, broker, persistence):
    order_id = engine.submit_signal("MATCH_ODDS", "2.200", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    engine.process_broker_outbox()

    event = FillEvent(event_id="persist-once", order_id=order_id, size=5.0, price=2.0)
    engine.process_event(event)
    engine.process_event(event)

    good_fill_rows = [row for _, row in persistence.rows if row.get("kind") == "fill" and row.get("event_id") == "persist-once"]
    assert len(good_fill_rows) == 1
    assert engine.state.orders[order_id].filled == 5.0


def test_unknown_fill_does_not_create_phantom_order(engine):
    ok = engine.process_event(FillEvent(event_id="ghost-fill", order_id="missing-order", size=10.0, price=2.0))
    assert ok is False
    assert "missing-order" not in engine.state.orders


def test_internal_state_reconciles_to_broker_source_of_truth(engine, broker):
    order_id = engine.submit_signal("MATCH_ODDS", "2.300", 1, "BACK", 2.0, 10.0, True, clock=1.0)
    engine.process_broker_outbox()

    broker.orders[order_id].price = 2.2
    broker.orders[order_id].size = 12.0
    broker.orders[order_id].version += 1

    engine.reconcile_from_broker()

    assert engine.state.orders[order_id].price == 2.2
    assert engine.state.orders[order_id].size == 12.0
    assert engine.state.orders[order_id].version == 1


@pytest.mark.parametrize(
    "ops",
    [
        ["submit", "fill5", "fill5"],
        ["submit", "fill3", "amend12", "fill9"],
        ["submit", "fill4", "cancel"],
        ["submit", "amend8", "fill8"],
    ],
)
def test_stateful_invariant_sweep(ops):
    broker = FakeBroker()
    persistence = FakePersistence()
    engine = ReferenceEngine(broker, persistence, EngineConfig(cooldown_seconds=0.0))

    order_id = None

    for op in ops:
        if op == "submit":
            order_id = engine.submit_signal("MATCH_ODDS", "2.400", 1, "BACK", 2.0, 10.0, True, clock=1.0)
            engine.process_broker_outbox()
        elif op == "fill5":
            broker.emit_fill(order_id, size=5.0, price=2.0, event_id=f"{op}-{len(engine.state.processed_event_ids)}")
            engine.process_broker_outbox()
        elif op == "fill3":
            broker.emit_fill(order_id, size=3.0, price=2.0, event_id=f"{op}-{len(engine.state.processed_event_ids)}")
            engine.process_broker_outbox()
        elif op == "fill4":
            broker.emit_fill(order_id, size=4.0, price=2.0, event_id=f"{op}-{len(engine.state.processed_event_ids)}")
            engine.process_broker_outbox()
        elif op == "fill8":
            broker.emit_fill(order_id, size=8.0, price=2.0, event_id=f"{op}-{len(engine.state.processed_event_ids)}")
            engine.process_broker_outbox()
        elif op == "fill9":
            broker.emit_fill(order_id, size=9.0, price=2.0, event_id=f"{op}-{len(engine.state.processed_event_ids)}")
            engine.process_broker_outbox()
        elif op == "amend12":
            engine.amend_order(order_id, new_size=12.0)
        elif op == "amend8":
            engine.amend_order(order_id, new_size=8.0)
        elif op == "cancel":
            engine.cancel_order(order_id)

    if order_id:
        order = engine.state.orders[order_id]
        assert 0.0 <= order.filled <= order.size
        assert engine.state.exposure >= 0.0
        assert all(v >= 0.0 for v in engine.state.position_by_selection.values())
        assert order.status in ("OPEN", "FILLED", "CANCELED", "REJECTED")