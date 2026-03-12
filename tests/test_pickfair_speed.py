import time

from ai.wom_engine import WoMEngine
from controllers.dutching_controller import DutchingController
from core.trading_engine import TradingEngine


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
        self.virtual_balance = 1000.0
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
            "starting_balance": 1000.0,
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
        return {
            "status": "SUCCESS",
            "instructionReports": [{"betId": "P1", "sizeMatched": 0.0}],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}

    def get_market_book(self, market_id):
        return {
            "marketId": market_id,
            "runners": [
                {
                    "selectionId": 1,
                    "ex": {
                        "availableToBack": [{"price": 2.0, "size": 10000.0}],
                        "availableToLay": [{"price": 2.02, "size": 10000.0}],
                    },
                },
                {
                    "selectionId": 2,
                    "ex": {
                        "availableToBack": [{"price": 3.0, "size": 10000.0}],
                        "availableToLay": [{"price": 3.05, "size": 10000.0}],
                    },
                },
            ],
        }


def make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: client, executor)
    return engine, bus, db, client


def test_wom_engine_1000_ticks_under_threshold():
    engine = WoMEngine()

    start = time.perf_counter()
    for _ in range(1000):
        engine.record_tick(101, 2.0, 400.0, 2.02, 250.0)
    result = engine.calculate_enhanced_wom(101)
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 0.25


def test_wom_engine_multi_runner_stress():
    engine = WoMEngine()

    start = time.perf_counter()
    for sel_id in range(1, 51):
        for _ in range(40):
            engine.record_tick(sel_id, 2.0, 300.0 + sel_id, 2.02, 200.0)
        assert engine.calculate_wom(sel_id) is not None
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0


def test_controller_preflight_speed():
    ctrl = DutchingController(bus=DummyBus(), simulation=True)

    selections = []
    for i in range(1, 21):
        selections.append(
            {
                "selectionId": i,
                "runnerName": f"Runner {i}",
                "price": 2.0 + (i * 0.05),
                "stake": 5.0,
                "back_ladder": [{"price": 2.0 + (i * 0.05), "size": 5000.0}],
                "lay_ladder": [{"price": 2.02 + (i * 0.05), "size": 5000.0}],
            }
        )

    start = time.perf_counter()
    result = ctrl.preflight_check(selections, total_stake=100.0, mode="BACK")
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 0.15


def test_controller_submit_dry_run_speed():
    bus = DummyBus()
    ctrl = DutchingController(bus=bus, simulation=True)
    ctrl.current_event_name = "Juve - Milan"
    ctrl.current_market_name = "Match Odds"

    selections = [
        {
            "selectionId": 1,
            "runnerName": "Juve",
            "price": 2.0,
            "stake": 10.0,
            "back_ladder": [{"price": 2.0, "size": 10000.0}],
            "lay_ladder": [{"price": 2.02, "size": 10000.0}],
        },
        {
            "selectionId": 2,
            "runnerName": "Milan",
            "price": 3.2,
            "stake": 10.0,
            "back_ladder": [{"price": 3.2, "size": 10000.0}],
            "lay_ladder": [{"price": 3.25, "size": 10000.0}],
        },
    ]

    start = time.perf_counter()
    result = ctrl.submit_dutching(
        market_id="1.100",
        market_type="MATCH_ODDS",
        selections=selections,
        total_stake=20.0,
        mode="BACK",
        dry_run=True,
    )
    elapsed = time.perf_counter() - start

    assert result["status"] == "DRY_RUN"
    assert elapsed < 0.20


def test_trading_engine_quick_bet_simulation_speed():
    engine, bus, db, client = make_engine()

    start = time.perf_counter()
    engine._handle_quick_bet(
        {
            "market_id": "1.200",
            "selection_id": 11,
            "bet_type": "BACK",
            "price": 2.5,
            "stake": 10.0,
            "event_name": "Juve - Milan",
            "market_name": "Match Odds",
            "runner_name": "Juve",
            "simulation_mode": True,
        }
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 0.05
    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["sim"] is True


def test_trading_engine_microstake_speed():
    engine, bus, db, client = make_engine()

    start = time.perf_counter()
    engine._handle_quick_bet(
        {
            "market_id": "1.201",
            "selection_id": 12,
            "bet_type": "BACK",
            "price": 2.12,
            "stake": 0.50,
            "event_name": "Inter - Roma",
            "market_name": "Match Odds",
            "runner_name": "Inter",
            "simulation_mode": False,
        }
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 0.10
    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1


def test_trading_engine_dutching_real_path_speed():
    engine, bus, db, client = make_engine()

    start = time.perf_counter()
    engine._handle_place_dutching(
        {
            "market_id": "1.202",
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
            "use_best_price": True,
        }
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 0.10
    assert len(client.place_orders_calls) == 1


def test_stress_100_quick_bets_simulation_under_threshold():
    engine, bus, db, client = make_engine()

    start = time.perf_counter()
    for i in range(100):
        engine._handle_quick_bet(
            {
                "market_id": f"1.{300+i}",
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

    assert elapsed < 0.50
    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 100