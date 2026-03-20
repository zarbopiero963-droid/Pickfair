import time

from ai.wom_engine import WoMEngine
from controllers.dutching_controller import DutchingController
from core.trading_engine import TradingEngine
from telegram_listener import SignalQueue


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}
        self.last_event = None

    def subscribe(self, name, fn):
        self.subscribers[name] = fn

    def publish(self, name, payload):
        self.last_event = (name, payload)
        self.events.append((name, payload))


class DummyDB:
    def __init__(self):
        self.saved_bets = []
        self.saved_cashouts = []
        self.pending = []
        self.virtual_balance = 100000.0
        self.bet_count = 0

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": payload,
            }
        )

    def get_pending_sagas(self):
        return list(self.pending)

    def mark_saga_reconciled(self, _customer_ref):
        return None

    def mark_saga_failed(self, _customer_ref):
        return None

    def save_bet(
        self,
        event_name,
        market_id,
        market_name,
        bet_type,
        selections,
        total_stake,
        potential_profit,
        status="PENDING",
    ):
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
        return {
            "virtual_balance": self.virtual_balance,
            "starting_balance": 100000.0,
            "bet_count": self.bet_count,
        }

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, new_balance):
        self.virtual_balance = float(new_balance)
        self.bet_count += 1


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyClient:
    def __init__(self):
        self.place_bet_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.place_orders_calls = []

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
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "B1", "sizeMatched": 0.0}],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {"market_id": market_id, "instructions": instructions or []}
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {"market_id": market_id, "instructions": instructions or []}
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "B1", "sizeMatched": 0.0}],
        }

    def place_orders(self, market_id=None, instructions=None, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
                "customer_ref": customer_ref,
            }
        )
        reports = []
        for i, instr in enumerate(instructions or [], start=1):
            reports.append(
                {
                    "betId": f"P{i}",
                    "selectionId": instr.get("selectionId"),
                    "sizeMatched": 0.0,
                }
            )
        return {"status": "SUCCESS", "instructionReports": reports}

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}

    def get_market_book(self, market_id):
        return {
            "marketId": market_id,
            "runners": [
                {
                    "selectionId": i,
                    "ex": {
                        "availableToBack": [{"price": 2.0 + (i * 0.01), "size": 100000.0}],
                        "availableToLay": [{"price": 2.02 + (i * 0.01), "size": 100000.0}],
                    },
                }
                for i in range(1, 11)
            ],
        }


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: client, executor)
    return engine, bus, db, client


def _make_controller(simulation=False):
    bus = DummyBus()
    ctrl = DutchingController(bus=bus, simulation=simulation)
    ctrl.current_event_name = "Stress Event"
    ctrl.current_market_name = "Match Odds"
    return ctrl, bus


def _selection_block(n=10):
    rows = []
    for i in range(1, n + 1):
        price = 2.0 + (i * 0.07)
        rows.append(
            {
                "selectionId": i,
                "runnerName": f"Runner {i}",
                "price": price,
                "stake": 2.0,
                "back_ladder": [{"price": price, "size": 50000.0}],
                "lay_ladder": [{"price": price + 0.02, "size": 50000.0}],
            }
        )
    return rows


def test_hft_wom_burst_1000_ticks():
    engine = WoMEngine()

    start = time.perf_counter()
    for i in range(1000):
        sel_id = (i % 20) + 1
        engine.record_tick(
            sel_id,
            2.0 + (sel_id * 0.01),
            100.0 + sel_id,
            2.02 + (sel_id * 0.01),
            80.0 + sel_id,
        )
    for sel_id in range(1, 21):
        result = engine.calculate_enhanced_wom(sel_id)
        if result is not None:
            assert result.tick_count >= 2
    elapsed = time.perf_counter() - start

    assert elapsed < 0.50


def test_hft_wom_burst_5000_ticks_same_runner():
    engine = WoMEngine(window_size=5000, time_window=120.0)

    start = time.perf_counter()
    for _ in range(5000):
        engine.record_tick(777, 2.0, 500.0, 2.02, 300.0)
    result = engine.calculate_enhanced_wom(777)
    elapsed = time.perf_counter() - start

    assert result is not None
    assert result.tick_count >= 2
    assert elapsed < 1.20


def test_hft_signal_queue_500_burst():
    queue = SignalQueue(max_size=1000)

    start = time.perf_counter()
    for i in range(500):
        queue.add(
            {
                "id": i,
                "selection": f"Runner {i}",
                "action": "BACK",
                "odds": 2.0,
                "stake": 2.0,
            }
        )
    pending = queue.get_pending()
    elapsed = time.perf_counter() - start

    assert len(pending) == 500
    assert elapsed < 0.10


def test_hft_signal_queue_saturation_keeps_latest_only():
    queue = SignalQueue(max_size=100)

    for i in range(300):
        queue.add({"id": i})

    pending = queue.get_pending()

    assert len(pending) == 100
    assert pending[0]["id"] == 200
    assert pending[-1]["id"] == 299


def test_hft_controller_flood_dry_run_200_requests():
    ctrl, bus = _make_controller(simulation=True)
    selections = _selection_block(3)

    start = time.perf_counter()
    for i in range(200):
        result = ctrl.submit_dutching(
            market_id=f"1.{1000 + i}",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=6.0,
            mode="BACK",
            dry_run=True,
        )
        assert result["status"] == "DRY_RUN"
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0


def test_hft_controller_publish_burst_100_requests():
    ctrl, bus = _make_controller(simulation=False)
    selections = _selection_block(2)

    start = time.perf_counter()
    for i in range(100):
        result = ctrl.submit_dutching(
            market_id=f"2.{2000 + i}",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=5.0,
            mode="BACK",
        )
        assert result["status"] == "SUBMITTED"
    elapsed = time.perf_counter() - start

    assert len(bus.events) == 100
    assert elapsed < 1.0


def test_hft_trading_engine_500_quick_bet_simulations():
    engine, bus, db, client = _make_engine()

    start = time.perf_counter()
    for i in range(500):
        engine._handle_quick_bet(
            {
                "market_id": f"3.{i}",
                "selection_id": i + 1,
                "bet_type": "BACK",
                "price": 2.0,
                "stake": 2.0,
                "event_name": f"Event {i}",
                "market_name": "Match Odds",
                "runner_name": f"Runner {i}",
                "simulation_mode": True,
            }
        )
    elapsed = time.perf_counter() - start

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 500
    assert elapsed < 1.50


def test_hft_trading_engine_microstake_burst_100():
    engine, bus, db, client = _make_engine()

    start = time.perf_counter()
    for i in range(100):
        engine._handle_quick_bet(
            {
                "market_id": f"4.{i}",
                "selection_id": i + 1,
                "bet_type": "BACK",
                "price": 2.10,
                "stake": 0.50,
                "event_name": f"Micro Event {i}",
                "market_name": "Match Odds",
                "runner_name": f"Runner {i}",
                "simulation_mode": False,
            }
        )
    elapsed = time.perf_counter() - start

    assert len(client.place_bet_calls) == 100
    assert len(client.cancel_orders_calls) == 100
    assert len(client.replace_orders_calls) == 100
    assert elapsed < 1.50


def test_hft_trading_engine_dutching_burst_100():
    engine, bus, db, client = _make_engine()
    results = [
        {"selectionId": 1, "runnerName": "A", "price": 2.0, "stake": 5.0},
        {"selectionId": 2, "runnerName": "B", "price": 3.0, "stake": 5.0},
    ]

    start = time.perf_counter()
    for i in range(100):
        engine._handle_place_dutching(
            {
                "market_id": f"5.{i}",
                "market_type": "MATCH_ODDS",
                "event_name": f"Dutch Event {i}",
                "market_name": "Match Odds",
                "bet_type": "BACK",
                "total_stake": 10.0,
                "results": results,
                "simulation_mode": False,
                "use_best_price": True,
            }
        )
    elapsed = time.perf_counter() - start

    success = [e for e in bus.events if e[0] == "DUTCHING_SUCCESS"]
    assert len(success) == 100
    assert len(client.place_orders_calls) == 100
    assert elapsed < 1.50


def test_hft_preflight_1000_cycles():
    ctrl, _ = _make_controller(simulation=True)
    selections = _selection_block(5)

    start = time.perf_counter()
    for _ in range(1000):
        result = ctrl.preflight_check(selections, total_stake=10.0, mode="BACK")
        assert result is not None
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0


def test_hft_guard_liquidity_500_cycles():
    ctrl, _ = _make_controller(simulation=True)
    selections = _selection_block(5)
    merged = ctrl._merge_ladders_to_results(
        [
            {
                "selectionId": s["selectionId"],
                "runnerName": s["runnerName"],
                "price": s["price"],
                "stake": 2.0,
                "side": "BACK",
                "effectiveType": "BACK",
            }
            for s in selections
        ],
        selections,
    )

    start = time.perf_counter()
    for _ in range(500):
        ok, msgs = ctrl._check_liquidity_guard(merged, mode="BACK", market_id="6.1")
        assert isinstance(ok, bool)
        assert isinstance(msgs, list)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0


def test_hft_event_bus_publish_10000_messages():
    bus = DummyBus()

    start = time.perf_counter()
    for i in range(10000):
        bus.publish("TICK_EVENT", {"i": i})
    elapsed = time.perf_counter() - start

    assert len(bus.events) == 10000
    assert elapsed < 0.50


def test_hft_combined_tick_to_controller_pipeline():
    wom = WoMEngine()
    ctrl, bus = _make_controller(simulation=False)
    selections = _selection_block(3)

    start = time.perf_counter()

    for _ in range(300):
        wom.record_tick(1, 2.0, 500.0, 2.02, 300.0)
        wom.record_tick(2, 3.0, 400.0, 3.05, 250.0)
        wom.record_tick(3, 4.0, 350.0, 4.1, 220.0)

    assert wom.calculate_enhanced_wom(1) is not None

    for _ in range(50):
        result = ctrl.submit_dutching(
            market_id="7.1",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=7.0,
            mode="BACK",
        )
        assert result["status"] == "SUBMITTED"

    elapsed = time.perf_counter() - start

    assert len(bus.events) == 50
    assert elapsed < 1.50