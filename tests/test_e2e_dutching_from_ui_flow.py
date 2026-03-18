import importlib
import sys
import types

from core.trading_engine import TradingEngine


def _install_ui_and_external_stubs():
    if "customtkinter" not in sys.modules:
        ctk = types.ModuleType("customtkinter")
        ctk.CTkFrame = object
        ctk.CTkLabel = object
        ctk.CTkOptionMenu = object
        ctk.CTkCheckBox = object
        ctk.CTkButton = object
        sys.modules["customtkinter"] = ctk

    if "betfairlightweight" not in sys.modules:
        bflw = types.ModuleType("betfairlightweight")
        bflw.APIClient = object
        bflw.exceptions = types.SimpleNamespace(
            LoginError=Exception,
            CertsError=Exception,
            APIError=Exception,
        )
        bflw.filters = types.SimpleNamespace(
            price_projection=lambda **kwargs: kwargs,
            market_filter=lambda **kwargs: kwargs,
            time_range=lambda **kwargs: kwargs,
        )
        sys.modules["betfairlightweight"] = bflw

    if "betfairlightweight.streaming" not in sys.modules:
        streaming = types.ModuleType("betfairlightweight.streaming")
        streaming.StreamListener = object
        sys.modules["betfairlightweight.streaming"] = streaming


_install_ui_and_external_stubs()

controller_mod = importlib.import_module("controllers.dutching_controller")
DutchingController = controller_mod.DutchingController


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
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending_sagas = []
        self.saved_bets = []
        self.reconciled = []
        self.failed = []
        self.sim_settings = {"virtual_balance": 1000.0}

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending_sagas.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": "{}",
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return []

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
        status,
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
        return dict(self.sim_settings)

    def save_simulation_bet(self, **kwargs):
        return kwargs

    def increment_simulation_bet_count(self, new_balance):
        self.sim_settings["virtual_balance"] = new_balance

    def save_cashout_transaction(self, **kwargs):
        return kwargs


class DummyClient:
    def __init__(self):
        self.place_orders_calls = []
        self.market_book = {
            "runners": [
                {
                    "selectionId": 11,
                    "ex": {"availableToBack": [{"price": 2.2, "size": 50}]},
                },
                {
                    "selectionId": 22,
                    "ex": {"availableToBack": [{"price": 3.1, "size": 30}]},
                },
            ]
        }

    def place_orders(self, market_id, instructions, customer_ref=None):
        self.place_orders_calls.append(
            {
                "market_id": market_id,
                "instructions": instructions,
                "customer_ref": customer_ref,
            }
        )
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {"betId": f"BET-{ins['selectionId']}", "sizeMatched": ins["limitOrder"]["size"]}
                for ins in instructions
            ],
        }

    def get_market_book(self, market_id):
        return self.market_book

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": [], "matched": [], "unmatched": []}


class DummySafeMode:
    def __init__(self):
        self.is_safe_mode_active = False

    def report_error(self, *args, **kwargs):
        return None

    def report_success(self):
        return None


class DummyGuardrail:
    def full_check(self, **kwargs):
        return {
            "can_proceed": True,
            "level": "normal",
            "reasons": [],
            "warnings": [],
            "blocked_until": 0,
        }


def test_e2e_dutching_from_ui_flow(monkeypatch):
    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    controller = DutchingController(bus=bus, simulation=False)
    controller.safe_mode = DummySafeMode()
    controller.guardrail = DummyGuardrail()

    monkeypatch.setattr(
        controller,
        "check_guardrail",
        lambda **kwargs: {
            "can_proceed": True,
            "level": "normal",
            "reasons": [],
            "warnings": [],
            "blocked_until": 0,
        },
    )

    monkeypatch.setattr(
        controller,
        "preflight_check",
        lambda selections, total_stake, mode="BACK": type(
            "PF",
            (),
            {
                "is_valid": True,
                "warnings": [],
                "errors": [],
                "details": {},
                "liquidity_ok": True,
                "liquidity_guard_ok": True,
                "spread_ok": True,
                "stake_ok": True,
                "price_ok": True,
                "book_ok": True,
            },
        )(),
    )

    monkeypatch.setattr(controller, "_check_liquidity_guard", lambda *a, **k: (True, []))

    res = controller.submit_dutching(
        market_id="1.999",
        market_type="MATCH_ODDS",
        event_name="Napoli - Lazio",
        market_name="Match Odds",
        selections=[
            {"selectionId": 11, "runnerName": "Napoli", "price": 2.0},
            {"selectionId": 22, "runnerName": "Lazio", "price": 3.0},
        ],
        total_stake=15.0,
        mode="BACK",
    )

    assert res["status"] == "SUBMITTED"

    req = [evt for evt in bus.events if evt[0] == "REQ_PLACE_DUTCHING"]
    assert len(req) == 1

    engine._handle_place_dutching(req[0][1])

    assert len(client.place_orders_calls) == 1
    assert len(db.saved_bets) == 1

    success = [evt for evt in bus.events if evt[0] == "DUTCHING_SUCCESS"]
    assert len(success) == 1

    evt = success[0][1]
    assert evt["market_id"] == "1.999"
    assert evt["event_name"] == "Napoli - Lazio"
    assert evt["market_name"] == "Match Odds"
    assert evt["status"] == "MATCHED"
    assert len(evt["selections"]) == 2