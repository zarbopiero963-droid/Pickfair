import importlib
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest


# =========================================================
# HELPERS
# =========================================================

class DummyBus:
    def __init__(self):
        self.subscribers = {}
        self.events = []

    def subscribe(self, event_name, callback):
        self.subscribers.setdefault(event_name, []).append(callback)

    def publish(self, event_name, payload):
        self.events.append((event_name, payload))
        for cb in self.subscribers.get(event_name, []):
            cb(payload)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.pending = []
        self.bets = []
        self.cashouts = []
        self.sim_bets = []
        self.outbox = []
        self.settings = {"virtual_balance": 10000.0, "bet_count": 0}
        self.telegram_settings = {"master_chat_id": "-100999"}
        self.reconciled = []
        self.failed = []

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload):
        self.pending.append(
            {
                "customer_ref": customer_ref,
                "market_id": market_id,
                "selection_id": selection_id,
                "raw_payload": json.dumps(payload),
                "status": "PENDING",
            }
        )

    def get_pending_sagas(self):
        return [p for p in self.pending if p["status"] == "PENDING"]

    def mark_saga_reconciled(self, customer_ref):
        self.reconciled.append(customer_ref)
        for row in self.pending:
            if row["customer_ref"] == customer_ref:
                row["status"] = "RECONCILED"

    def mark_saga_failed(self, customer_ref):
        self.failed.append(customer_ref)
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

    def save_cashout_transaction(self, **kwargs):
        self.cashouts.append(kwargs)

    def get_simulation_settings(self):
        return dict(self.settings)

    def increment_simulation_bet_count(self, new_balance):
        self.settings["virtual_balance"] = float(new_balance)
        self.settings["bet_count"] = int(self.settings.get("bet_count", 0)) + 1

    def save_simulation_bet(self, **kwargs):
        self.sim_bets.append(kwargs)

    def save_telegram_outbox_log(self, **kwargs):
        self.outbox.append(kwargs)

    def get_telegram_settings(self):
        return dict(self.telegram_settings)


class DummyClient:
    def __init__(self):
        self.place_bet_calls = []
        self.place_orders_calls = []
        self.cancel_orders_calls = []
        self.replace_orders_calls = []
        self.current_orders = []

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

        size_matched = 0.0 if float(size) == 2.0 else float(size)

        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{customer_ref or 'X'}",
                    "sizeMatched": size_matched,
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
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": f"BET-{customer_ref or 'X'}-{idx}",
                    "sizeMatched": float(ins["limitOrder"]["size"]),
                }
                for idx, ins in enumerate(instructions or [], start=1)
            ],
        }

    def cancel_orders(self, market_id=None, instructions=None):
        self.cancel_orders_calls.append(
            {"market_id": market_id, "instructions": instructions}
        )
        return {"status": "SUCCESS", "instructionReports": []}

    def replace_orders(self, market_id=None, instructions=None):
        self.replace_orders_calls.append(
            {"market_id": market_id, "instructions": instructions}
        )
        bet_id = ""
        if instructions:
            bet_id = instructions[0].get("betId", "")
        return {
            "status": "SUCCESS",
            "instructionReports": [
                {
                    "betId": bet_id or "BET-REPLACED",
                    "sizeMatched": 0.5,
                }
            ],
        }

    def get_current_orders(self, *args, **kwargs):
        return {"currentOrders": list(self.current_orders), "matched": [], "unmatched": []}

    def get_market_book(self, market_id):
        return {
            "runners": [
                {
                    "selectionId": 11,
                    "ex": {
                        "availableToBack": [{"price": 2.20, "size": 100}],
                        "availableToLay": [{"price": 2.24, "size": 100}],
                    },
                },
                {
                    "selectionId": 22,
                    "ex": {
                        "availableToBack": [{"price": 3.10, "size": 100}],
                        "availableToLay": [{"price": 3.15, "size": 100}],
                    },
                },
            ]
        }


class DummyTelegramClient:
    def __init__(self):
        self.sent = []

    async def get_entity(self, chat_id):
        return types.SimpleNamespace(id=chat_id)

    async def send_message(self, entity, text):
        msg = types.SimpleNamespace(id=len(self.sent) + 1)
        self.sent.append((entity.id, text))
        return msg


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyUIQ:
    def post(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


# =========================================================
# 1) REAL SMOKE SU main.py
# =========================================================

def test_real_smoke_main_import(monkeypatch):
    fake_ctk = types.ModuleType("customtkinter")

    class _Widget:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def place(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def pack_propagate(self, *args, **kwargs):
            return None

        def winfo_exists(self):
            return True

    class _Root(_Widget):
        def title(self, *args, **kwargs):
            return None

        def geometry(self, *args, **kwargs):
            return None

        def minsize(self, *args, **kwargs):
            return None

        def resizable(self, *args, **kwargs):
            return None

        def after(self, *args, **kwargs):
            return None

        def iconbitmap(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def winfo_screenwidth(self):
            return 1400

        def winfo_screenheight(self):
            return 900

        def winfo_x(self):
            return 0

        def winfo_y(self):
            return 0

        def winfo_width(self):
            return 1200

        def winfo_height(self):
            return 800

    fake_ctk.CTk = _Root
    fake_ctk.CTkFrame = _Widget
    fake_ctk.CTkLabel = _Widget
    fake_ctk.CTkButton = _Widget
    fake_ctk.CTkEntry = _Widget
    fake_ctk.CTkCheckBox = _Widget
    fake_ctk.CTkRadioButton = _Widget
    fake_ctk.CTkScrollableFrame = _Widget
    fake_ctk.CTkToplevel = _Root
    fake_ctk.DISABLED = "disabled"
    fake_ctk.NORMAL = "normal"

    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)

    main = importlib.import_module("main")
    assert main is not None
    assert hasattr(main, "PickfairApp")


# =========================================================
# 2) TEST UI BASE NON GRAFICI
# =========================================================

def test_ui_base_non_graphic_telegram_tab_import_and_build(monkeypatch):
    fake_ctk = types.ModuleType("customtkinter")

    class _Widget:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def place(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def pack_propagate(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def yview(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

        def bbox(self, *args, **kwargs):
            return (0, 0, 100, 100)

        def winfo_exists(self):
            return True

        def delete(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def heading(self, *args, **kwargs):
            return None

        def column(self, *args, **kwargs):
            return None

    fake_ctk.CTkFrame = _Widget
    fake_ctk.CTkLabel = _Widget
    fake_ctk.CTkButton = _Widget
    fake_ctk.CTkEntry = _Widget
    fake_ctk.CTkCheckBox = _Widget
    fake_ctk.CTkScrollableFrame = _Widget

    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)

    import tkinter as tk
    from tkinter import ttk

    class DummyTree:
        def heading(self, *args, **kwargs):
            return None

        def column(self, *args, **kwargs):
            return None

        def pack(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def selection(self):
            return ()

        def item(self, *args, **kwargs):
            return {"values": []}

        def tag_configure(self, *args, **kwargs):
            return None

        def winfo_exists(self):
            return True

        def yview(self, *args, **kwargs):
            return None

    monkeypatch.setattr(ttk, "Treeview", lambda *a, **k: DummyTree())
    monkeypatch.setattr(ttk, "Scrollbar", lambda *a, **k: _Widget())
    monkeypatch.setattr(tk, "Canvas", lambda *a, **k: _Widget())

    mod = importlib.import_module("ui.tabs.telegram_tab_ui")
    TelegramTabUI = mod.TelegramTabUI

    class DummyApp:
        def __init__(self):
            self.db = types.SimpleNamespace(get_telegram_settings=lambda: {}, get_telegram_chats=lambda: [], get_signal_patterns=lambda: [])
            self.telegram_controller = types.SimpleNamespace(
                send_code=lambda: None,
                verify_code=lambda: None,
                reset_session=lambda: None,
                save_settings=lambda: None,
                load_dialogs=lambda: None,
            )
            self.telegram_status = "STOPPED"

        def _start_telegram_listener(self):
            return None

        def _stop_telegram_listener(self):
            return None

        def _refresh_telegram_chats_tree(self):
            return None

        def _refresh_rules_tree(self):
            return None

        def _refresh_telegram_signals_tree(self):
            return None

        def _remove_telegram_chat(self):
            return None

        def _add_selected_available_chats(self):
            return None

        def _add_signal_pattern(self):
            return None

        def _edit_signal_pattern(self):
            return None

        def _delete_signal_pattern(self):
            return None

        def _toggle_signal_pattern(self):
            return None

    app = DummyApp()
    ui = TelegramTabUI(parent_frame=_Widget(), app=app)
    assert ui is not None
    assert hasattr(app, "tg_api_id_var")
    assert hasattr(app, "tg_signals_tree")


# =========================================================
# 3) TEST DB MIGRATION VECCHIO -> NUOVO
# =========================================================

def test_db_migration_old_to_new(tmp_path, monkeypatch):
    legacy_db = tmp_path / "legacy.sqlite"

    conn = sqlite3.connect(legacy_db)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        """
        CREATE TABLE telegram_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            api_id TEXT,
            api_hash TEXT,
            session_string TEXT,
            phone_number TEXT,
            enabled INTEGER DEFAULT 0,
            auto_bet INTEGER DEFAULT 0,
            require_confirmation INTEGER DEFAULT 1,
            auto_stake REAL DEFAULT 1.0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO telegram_settings
        (id, api_id, api_hash, session_string, phone_number, enabled, auto_bet, require_confirmation, auto_stake)
        VALUES (1, '123', 'hash', 'sess', '+39000', 1, 1, 0, 2.5)
        """
    )
    conn.commit()
    conn.close()

    db_mod = importlib.import_module("database")
    monkeypatch.setattr(db_mod, "get_db_path", lambda: str(legacy_db))

    db = db_mod.Database()
    try:
        db.save_telegram_settings({"api_id": "999", "master_chat_id": "-100555", "enabled": 1})
        settings = db.get_telegram_settings()

        assert settings["api_id"] == "999"
        assert settings["master_chat_id"] == "-100555"
        assert settings["publisher_chat_id"] == "-100555"
    finally:
        db.close()


# =========================================================
# 4) TEST TELEGRAM MASTER/FOLLOWER END-TO-END
# =========================================================

def test_telegram_master_follower_end_to_end(monkeypatch):
    sender_mod = importlib.import_module("telegram_sender")
    listener_mod = importlib.import_module("telegram_listener")

    bus = DummyBus()
    db = DummyDB()
    tg_client = DummyTelegramClient()

    sender = sender_mod.TelegramSender(
        client=tg_client,
        event_bus=bus,
        default_chat_id="-100999",
        db=db,
        base_delay=0.0,
    )

    # Simula master event → telegram_sender formatta messaggio
    bus.publish(
        "QUICK_BET_SUCCESS",
        {
            "sim": False,
            "runner_name": "Juve",
            "bet_type": "BACK",
            "price": 2.15,
            "market_id": "1.234",
            "selection_id": 55,
            "event_name": "Juve - Milan",
            "market_name": "Match Odds",
            "status": "MATCHED",
        },
    )

    # svuota coda se il worker è partito
    sender.stop_worker()

    assert len(tg_client.sent) >= 1
    text = tg_client.sent[-1][1]
    assert "MASTER SIGNAL" in text
    assert "selection: Juve" in text
    assert "market_id: 1.234" in text

    # Simula follower parse dello stesso messaggio
    listener = listener_mod.TelegramListener(api_id=1, api_hash="hash")
    signal = listener.parse_signal(text)

    assert signal is not None
    assert signal["action"] == "BACK"
    assert signal["selection"] == "Juve"
    assert signal["market_id"] == "1.234"
    assert signal["selection_id"] == 55
    assert signal["match"] == "Juve - Milan"
    assert signal["market"] == "Match Odds"


# =========================================================
# 5) TEST DUTCHING UI -> CONTROLLER -> RISK -> ENGINE
# =========================================================

def test_dutching_ui_controller_risk_engine_flow(monkeypatch):
    risk_mod = importlib.import_module("core.risk_middleware")
    engine_mod = importlib.import_module("core.trading_engine")
    ctrl_mod = importlib.import_module("controllers.dutching_controller")

    bus = DummyBus()
    db = DummyDB()
    executor = DummyExecutor()
    client = DummyClient()

    # middleware + engine reali
    risk_mod.RiskMiddleware(bus, None, None)
    engine_mod.TradingEngine(bus, db, lambda: client, executor)

    # patch controller deps non sempre disponibili
    class DummySafeMode:
        is_safe_mode_active = False

        def report_error(self, *args, **kwargs):
            return None

        def report_success(self):
            return None

    class DummyAIEngine:
        def decide(self, selections):
            return {s["selectionId"]: "BACK" for s in selections}

        def get_wom_analysis(self, selections):
            return []

        def get_enhanced_analysis(self, selections, wom_engine):
            return []

    class DummyWomEngine:
        def calculate_enhanced_wom(self, selection_id):
            return None

        def record_tick(self, *args, **kwargs):
            return None

        def get_stats(self):
            return {}

        def get_time_window_signal(self, selection_id):
            return {}

    class DummyGuardrail:
        def full_check(self, **kwargs):
            return {"can_proceed": True}

        def check_auto_green_grace(self, bet_id):
            return True

        def register_order_for_auto_green(self, bet_id):
            return None

        def get_status(self):
            return {}

    class DummyMarketValidator:
        def is_dutching_ready(self, market_type):
            return True

    class DummyAutomationEngine:
        def __init__(self, controller):
            self.controller = controller

    monkeypatch.setattr(ctrl_mod, "AIPatternEngine", lambda: DummyAIEngine())
    monkeypatch.setattr(ctrl_mod, "get_wom_engine", lambda: DummyWomEngine())
    monkeypatch.setattr(ctrl_mod, "get_guardrail", lambda: DummyGuardrail())
    monkeypatch.setattr(ctrl_mod, "MarketValidator", lambda: DummyMarketValidator())
    monkeypatch.setattr(ctrl_mod, "AutomationEngine", DummyAutomationEngine)
    monkeypatch.setattr(ctrl_mod, "get_safe_mode_manager", lambda: DummySafeMode())
    monkeypatch.setattr(ctrl_mod, "get_safety_logger", lambda: object())

    controller = ctrl_mod.DutchingController(bus=bus, simulation=False)
    controller.current_event_name = "Napoli - Lazio"
    controller.current_market_name = "Match Odds"

    result = controller.submit_dutching(
        market_id="1.999",
        market_type="MATCH_ODDS",
        selections=[
            {"selectionId": 11, "runnerName": "Napoli", "price": 2.0},
            {"selectionId": 22, "runnerName": "Lazio", "price": 3.0},
        ],
        total_stake=15.0,
        mode="BACK",
        dry_run=False,
    )

    assert result["status"] == "SUBMITTED"
    assert any(evt[0] == "REQ_PLACE_DUTCHING" for evt in bus.events)
    assert any(evt[0] == "CMD_PLACE_DUTCHING" for evt in bus.events)
    assert any(evt[0] == "DUTCHING_SUCCESS" for evt in bus.events)
    assert len(db.bets) >= 1


# =========================================================
# 6) TEST CRASH RECOVERY SAGHE PENDENTI
# =========================================================

def test_crash_recovery_pending_sagas(monkeypatch):
    engine_mod = importlib.import_module("core.trading_engine")

    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()
    executor = DummyExecutor()

    # saga pendente legacy/recupero
    db.pending.append(
        {
            "customer_ref": "RECOV123",
            "market_id": "1.777",
            "selection_id": 11,
            "raw_payload": json.dumps(
                {
                    "event_name": "Recovered Match",
                    "market_name": "Match Odds",
                    "bet_type": "BACK",
                    "stake": 10.0,
                    "price": 2.2,
                    "selection_id": 11,
                    "runner_name": "Recovered Runner",
                }
            ),
            "status": "PENDING",
        }
    )

    # l'ordine esiste già lato exchange
    client.current_orders = [
        {
            "customerOrderRef": "RECOV123",
            "marketId": "1.777",
            "betId": "BET-RECOVERED",
            "sizeMatched": 10.0,
        }
    ]

    engine = engine_mod.TradingEngine(bus, db, lambda: client, executor)

    submitted_tasks = []

    class InlineRecoveryExecutor:
        def submit(self, fn, *args, **kwargs):
            submitted_tasks.append(True)
            return fn(*args, **kwargs)

    engine.recovery_executor = InlineRecoveryExecutor()

    engine._recover_pending_sagas()

    assert submitted_tasks
    assert "RECOV123" in db.reconciled
    assert not db.failed
    assert len(db.bets) >= 1
    assert db.bets[-1]["market_id"] == "1.777"