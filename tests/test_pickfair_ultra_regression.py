import time

from ai.wom_engine import WoMEngine
from controllers.dutching_controller import DutchingController
from core.trading_engine import TradingEngine
from database import Database
from telegram_listener import TelegramListener


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def subscribe(self, name, fn):
        self.subscribers[name] = fn

    def publish(self, name, payload):
        self.events.append((name, payload))
        self.last_event = (name, payload)


class DummyDB:
    def __init__(self):
        self.saved_bets = []
        self.pending = []
        self.reconciled = []
        self.failed = []
        self.saved_cashouts = []
        self.sim_bets = []
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

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)

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

    def get_simulation_settings(self):
        return {
            "virtual_balance": self.virtual_balance,
            "starting_balance": 1000.0,
            "bet_count": self.bet_count,
        }

    def save_simulation_bet(self, **kwargs):
        self.sim_bets.append(kwargs)

    def increment_simulation_bet_count(self, new_balance):
        self.virtual_balance = float(new_balance)
        self.bet_count += 1

    def save_cashout_transaction(self, **kwargs):
        self.saved_cashouts.append(kwargs)


class DummyExecutor:
    def submit(self, _name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyClient:
    def __init__(self):
        self.place_bet_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.place_orders_calls = []
        self.orders_to_recover = []

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
            "instructionReports": [
                {
                    "betId": "BETX",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
            }
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions or [],
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": "BETX",
                    "sizeMatched": 0.0,
                }
            ],
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
            "instructionReports": [
                {
                    "betId": "PO1",
                    "sizeMatched": 0.0,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {
            "currentOrders": list(self.orders_to_recover),
            "matched": [],
            "unmatched": [],
        }

    def get_market_book(self, market_id):
        return {
            "marketId": market_id,
            "runners": [
                {
                    "selectionId": 1,
                    "ex": {
                        "availableToBack": [{"price": 2.0, "size": 1000.0}],
                        "availableToLay": [{"price": 2.02, "size": 1000.0}],
                    },
                }
            ],
        }


def _make_engine():
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()
    engine = TradingEngine(bus, db, lambda: client, executor)
    return engine, bus, db, client


def test_wom_no_data_insufficient_data():
    engine = WoMEngine()

    assert engine.calculate_wom(1) is None

    engine.record_tick(1, 2.0, 100.0, 2.02, 100.0)
    assert engine.calculate_wom(1) is None


def test_wom_strong_back_and_strong_lay():
    engine = WoMEngine()

    for _ in range(6):
        engine.record_tick(10, 2.0, 900.0, 2.02, 100.0)
        engine.record_tick(20, 2.0, 100.0, 2.02, 900.0)
        time.sleep(0.005)

    back_result = engine.calculate_enhanced_wom(10)
    lay_result = engine.calculate_enhanced_wom(20)

    assert back_result is not None
    assert lay_result is not None
    assert back_result.suggested_side == "BACK"
    assert lay_result.suggested_side == "LAY"


def test_trading_engine_microstake_full_flow_regression():
    engine, bus, db, client = _make_engine()

    engine._handle_quick_bet(
        {
            "market_id": "1.100",
            "selection_id": 11,
            "bet_type": "BACK",
            "price": 2.10,
            "stake": 0.50,
            "event_name": "A - B",
            "market_name": "Match Odds",
            "runner_name": "A",
            "simulation_mode": False,
        }
    )

    assert len(client.place_bet_calls) == 1
    assert len(client.cancel_orders_calls) == 1
    assert len(client.replace_orders_calls) == 1

    success = [e for e in bus.events if e[0] == "QUICK_BET_SUCCESS"]
    assert len(success) == 1
    assert success[0][1]["micro"] is True
    assert success[0][1]["bet_type"] == "BACK"


def test_trading_engine_recovery_of_pending_saga_regression():
    engine, bus, db, client = _make_engine()

    db.pending = [
        {
            "customer_ref": "ref1",
            "market_id": "1.200",
            "selection_id": "9",
            "raw_payload": (
                '{"stake": 10.0, "price": 2.0, "bet_type": "BACK", '
                '"runner_name": "Juve", "event_name": "Juve - Milan", '
                '"market_name": "Match Odds", "selection_id": 9}'
            ),
        }
    ]

    client.orders_to_recover = [
        {
            "customerOrderRef": "ref1",
            "marketId": "1.200",
            "sizeMatched": 10.0,
            "price": 2.0,
            "sizeRemaining": 0.0,
        }
    ]

    engine._recover_pending_sagas()

    assert "ref1" in db.reconciled
    assert len(db.saved_bets) == 1


def test_controller_publish_payload_complete_regression():
    bus = DummyBus()
    ctrl = DutchingController(bus=bus, simulation=False)

    ctrl.current_event_name = "Juve - Milan"
    ctrl.current_market_name = "Match Odds"

    result = ctrl.submit_dutching(
        market_id="1.300",
        market_type="MATCH_ODDS",
        selections=[
            {
                "selectionId": 1,
                "runnerName": "Juve",
                "price": 2.0,
                "stake": 10.0,
                "back_ladder": [{"price": 2.0, "size": 1000.0}],
                "lay_ladder": [{"price": 2.02, "size": 1000.0}],
            }
        ],
        total_stake=10.0,
        mode="BACK",
    )

    assert result["status"] == "SUBMITTED"
    assert hasattr(bus, "last_event")

    event_name, payload = bus.last_event
    assert event_name == "REQ_PLACE_DUTCHING"
    assert payload["market_id"] == "1.300"
    assert payload["event_name"] == "Juve - Milan"
    assert payload["market_name"] == "Match Odds"
    assert payload["bet_type"] == "BACK"
    assert "results" in payload
    assert "analytics" in payload
    assert "preflight" in payload


def test_telegram_listener_parse_master_and_legacy_regression():
    listener = TelegramListener(api_id=12345, api_hash="hash")

    master = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11\n"
    )

    legacy = (
        "🆚 Juve - Milan\n"
        "Over 2.5\n"
        "@ 2.10\n"
        "stake 10\n"
        "punta"
    )

    res_master = listener.parse_signal(master)
    res_legacy = listener.parse_signal(legacy)

    assert res_master is not None
    assert res_master["market_id"] == "1.123"
    assert res_master["selection_id"] == 11
    assert res_master["side"] == "BACK"

    assert res_legacy is not None
    assert res_legacy["side"] == "BACK"
    assert res_legacy["selection"] == "Over 2.5"


def test_database_clear_session_and_save_password_none_regression(tmp_path):
    db = Database(db_path=str(tmp_path / "ultra.db"))

    db.save_settings({"theme": "dark", "version": "1.0"})
    db.save_password("pass123")
    db.save_session("tok123", "exp123")

    settings = db.get_settings()
    assert settings["password"] == "pass123"
    assert settings["session_token"] == "tok123"

    db.clear_session()
    settings2 = db.get_settings()
    assert "session_token" not in settings2
    assert "session_expiry" not in settings2

    db.save_password(None)
    settings3 = db.get_settings()
    assert "password" not in settings3