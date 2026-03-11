import importlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace


# =========================================================
# HELPERS
# =========================================================

class DummyBus:
    def __init__(self):
        self.events = []

    def subscribe(self, event_name, callback):
        # minimal stub per TradingEngine
        return None

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        # esegue subito per rendere il test deterministico
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending = []
        self.bets = []
        self.cashouts = []
        self.sim_settings = {"virtual_balance": 10000.0, "bet_count": 0}

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": "{}",
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return [p for p in self.pending if p["status"] == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        for row in self.pending:
            if row["customer_ref"] == customer_ref:
                row["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        for row in self.pending:
            if row["customer_ref"] == customer_ref:
                row["status"] = "FAILED"

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
        self.bets.append(
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

    def save_cashout_transaction(
        self,
        market_id,
        selection_id,
        original_bet_id,
        cashout_bet_id,
        original_side,
        original_stake,
        original_price,
        cashout_side,
        cashout_stake,
        cashout_price,
        profit_loss,
    ):
        self.cashouts.append(
            {
                "market_id": market_id,
                "selection_id": selection_id,
                "cashout_bet_id": cashout_bet_id,
                "cashout_side": cashout_side,
                "cashout_stake": cashout_stake,
                "cashout_price": cashout_price,
                "profit_loss": profit_loss,
            }
        )

    def get_simulation_settings(self):
        return dict(self.sim_settings)

    def increment_simulation_bet_count(self, new_balance):
        self.sim_settings["virtual_balance"] = float(new_balance)
        self.sim_settings["bet_count"] = int(self.sim_settings.get("bet_count", 0)) + 1

    def save_simulation_bet(self, **kwargs):
        self.bets.append({"sim": True, **kwargs})


class DummyClient:
    def __init__(self, mode="ok"):
        self.mode = mode

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
        if self.mode == "network_down":
            raise RuntimeError("network down")
        if self.mode == "db_locked":
            raise RuntimeError("database is locked")
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{customer_ref or 'X'}",
                    "sizeMatched": float(size),
                }
            ],
        }

    def place_orders(self, market_id, instructions, customer_ref=None):
        if self.mode == "network_down":
            raise RuntimeError("network down")
        reports = []
        for i, ins in enumerate(instructions or [], start=1):
            reports.append(
                {
                    "betId": f"BET-{customer_ref or 'X'}-{i}",
                    "sizeMatched": float(ins.get("limitOrder", {}).get("size", 0.0)),
                }
            )
        return {
            "status": "SUCCESS",
            "instructionReports": reports,
        }

    def cancel_orders(self, market_id=None, instructions=None):
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        return {"status": "SUCCESS", "instructionReports": []}

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}

    def get_market_book(self, market_id):
        return {
            "runners": [
                {
                    "selectionId": 1,
                    "ex": {
                        "availableToBack": [{"price": 2.0, "size": 500}],
                        "availableToLay": [{"price": 2.02, "size": 500}],
                    },
                },
                {
                    "selectionId": 2,
                    "ex": {
                        "availableToBack": [{"price": 3.0, "size": 500}],
                        "availableToLay": [{"price": 3.05, "size": 500}],
                    },
                },
            ]
        }


class DummyTelegramClient:
    def __init__(self, flood=False):
        self.flood = flood
        self.sent = []

    async def get_entity(self, chat_id):
        return SimpleNamespace(id=chat_id)

    async def send_message(self, entity, text):
        if self.flood:
            raise RuntimeError("FloodWaitError: A wait of 12 seconds is required")
        msg = SimpleNamespace(id=len(self.sent) + 1)
        self.sent.append((entity.id, text))
        return msg


# =========================================================
# TESTS
# =========================================================

def test_py_compile_and_smoke_import_core():
    modules = [
        "database",
        "dutching",
        "telegram_listener",
        "telegram_sender",
        "core.trading_engine",
        "core.risk_middleware",
        "controllers.dutching_controller",
        "app_modules.telegram_module",
    ]
    for module_name in modules:
        mod = importlib.import_module(module_name)
        assert mod is not None


def test_trading_engine_quick_bet_simulation():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.100",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.10,
        "stake": 10.0,
        "event_name": "A - B",
        "market_name": "MATCH_ODDS",
        "runner_name": "Home",
    }

    engine._handle_quick_bet(payload)

    assert any(evt[0] == "QUICK_BET_SUCCESS" for evt in bus.events)
    assert len(db.bets) >= 1
    assert db.bets[-1]["status"] in ("MATCHED", "PARTIALLY_MATCHED")


def test_trading_engine_micro_stake_path():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.101",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.20,
        "stake": 0.50,  # micro-stake
        "event_name": "C - D",
        "market_name": "MATCH_ODDS",
        "runner_name": "Away",
    }

    engine._handle_quick_bet(payload)

    assert any(evt[0] == "QUICK_BET_SUCCESS" for evt in bus.events)
    last_event = [evt for evt in bus.events if evt[0] == "QUICK_BET_SUCCESS"][-1]
    assert last_event[1].get("micro") is True


def test_trading_engine_dutching_simulation():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.102",
        "market_type": "MATCH_ODDS",
        "event_name": "E - F",
        "market_name": "MATCH_ODDS",
        "bet_type": "BACK",
        "total_stake": 25.0,
        "results": [
            {"selectionId": 1, "runnerName": "One", "price": 2.0, "stake": 10.0},
            {"selectionId": 2, "runnerName": "Two", "price": 3.0, "stake": 15.0},
        ],
    }

    engine._handle_place_dutching(payload)

    assert any(evt[0] == "DUTCHING_SUCCESS" for evt in bus.events)
    assert len(db.bets) >= 1


def test_trading_engine_cashout_simulation():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.103",
        "selection_id": 1,
        "side": "LAY",
        "stake": 5.0,
        "price": 1.80,
        "green_up": 2.50,
    }

    engine._handle_cashout(payload)

    assert any(evt[0] == "CASHOUT_SUCCESS" for evt in bus.events)
    assert len(db.cashouts) == 1


def test_chaos_network_down():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient(mode="network_down")

    engine = TradingEngine(bus, db, lambda: client, executor)

    payload = {
        "market_id": "1.104",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.00,
        "stake": 10.0,
        "event_name": "X - Y",
        "market_name": "MATCH_ODDS",
        "runner_name": "Runner",
    }

    engine._handle_quick_bet(payload)

    assert any(evt[0] == "QUICK_BET_FAILED" for evt in bus.events)


def test_telegram_sender_ok_and_floodwait():
    telegram_sender = importlib.import_module("telegram_sender")
    init_telegram_sender = telegram_sender.init_telegram_sender

    ok_client = DummyTelegramClient(flood=False)
    sender = init_telegram_sender(client=ok_client, base_delay=0.0)
    result = sender.send_message_sync("12345", "hello", max_retries=1)
    assert result.success is True

    flood_client = DummyTelegramClient(flood=True)
    sender2 = telegram_sender.TelegramSender(flood_client, base_delay=0.0)
    result2 = sender2.send_message_sync("12345", "hello", max_retries=1)
    assert result2.success is False
    assert result2.flood_wait is not None


def test_latency_signal_to_execution_under_threshold():
    from core.trading_engine import TradingEngine

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, executor)

    start = time.perf_counter()

    payload = {
        "market_id": "1.105",
        "selection_id": 1,
        "bet_type": "BACK",
        "price": 2.30,
        "stake": 10.0,
        "event_name": "Latency - Test",
        "market_name": "MATCH_ODDS",
        "runner_name": "LatencyRunner",
    }

    engine._handle_quick_bet(payload)

    elapsed = time.perf_counter() - start

    assert any(evt[0] == "QUICK_BET_SUCCESS" for evt in bus.events)
    assert elapsed < 2.0


def test_stress_1000_signals():
    from dutching import calculate_dutching_stakes

    def worker(i: int):
        selections = [
            {"selectionId": 1, "runnerName": f"A{i}", "price": 2.0},
            {"selectionId": 2, "runnerName": f"B{i}", "price": 3.0},
        ]
        result, profit, book = calculate_dutching_stakes(
            selections=selections,
            total_stake=100.0,
            bet_type="BACK",
            commission=4.5,
        )
        return len(result), profit, book

    futures = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i in range(1000):
            futures.append(ex.submit(worker, i))

        completed = 0
        for fut in as_completed(futures):
            rows, profit, book = fut.result()
            assert rows == 2
            assert isinstance(profit, float)
            assert isinstance(book, float)
            completed += 1

    assert completed == 1000