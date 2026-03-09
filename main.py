"""
Betfair Dutching - Tutti i Mercati
Main application orchestrator.
"""
import logging
import threading
import time

import customtkinter as ctk

from ui.tabs.telegram_tab_ui import TelegramTabUI
from app_modules.betting_module import BettingModule
from app_modules.monitoring_module import MonitoringModule
from app_modules.simulation_module import SimulationModule
from app_modules.streaming_module import StreamingModule
from app_modules.telegram_module import TelegramModule
from app_modules.ui_module import UIModule
from controllers.telegram_controller import TelegramController
from core.event_bus import EventBus
from core.trading_engine import TradingEngine
from database import Database
from executor_manager import SafeExecutor
from goal_engine_pro import APIFootballClient, GoalEnginePro
from shutdown_manager import ShutdownManager
from telegram_listener import SignalQueue
from theme import COLORS
from tree_manager import TreeManager
from ui_queue import UIQueue

APP_NAME = "Pickfair"
APP_VERSION = "3.19.1"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900


class PickfairApp(
    UIModule,
    TelegramModule,
    StreamingModule,
    BettingModule,
    SimulationModule,
    MonitoringModule,
):
    def __init__(self):
        from theme import configure_customtkinter

        configure_customtkinter()
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.configure(fg_color=COLORS["bg_dark"])

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        available_height = screen_height - 50
        window_width = min(WINDOW_WIDTH, int(screen_width * 0.9))
        window_height = min(WINDOW_HEIGHT, int(available_height * 0.9))
        x = (screen_width - window_width) // 2
        y = max(0, (available_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(min_width=900, min_height=500)
        self.root.resizable(True, True)

        if screen_width <= 1366 or screen_height <= 768:
            self.root.after(100, lambda: self._try_maximize())

        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass

        self.logger = logging.getLogger("PickfairApp")

        self.db = Database()
        print(f"[DEBUG] Database path: {self.db.db_path}")

        self.bus = EventBus()

        # --- SAFE MODE GLOBAL KILL SWITCH BRIDGE ---
        self.safe_mode_active = False
        self.bus.subscribe("SAFE_MODE_TRIGGER", self._on_safe_mode_trigger)

        if hasattr(self, "_handle_telegram_signal"):
            self.bus.subscribe("TELEGRAM_SIGNAL", self._handle_telegram_signal)

        self.bus.subscribe(
            "TELEGRAM_STATUS",
            lambda data: self._update_telegram_status(data["status"], data["message"])
            if hasattr(self, "_update_telegram_status")
            else None,
        )
        self.bus.subscribe("MARKET_TICK", self._buffer_market_tick)

        self.client = None
        self.current_event = None
        self.current_market = None
        self.available_markets = []
        self.selected_runners = {}
        self.streaming_active = False
        self.live_mode = False
        self.live_refresh_id = None
        self.booking_monitor_id = None
        self.auto_cashout_monitor_id = None
        self.pending_bookings = []
        self.account_data = {"available": 0, "exposure": 0, "total": 0}
        self.telegram_listener = None
        self.telegram_signal_queue = SignalQueue()
        self.telegram_status = "STOPPED"
        self.market_status = "OPEN"
        self.simulation_mode = False

        self._buffer_lock = threading.Lock()
        self._market_update_buffer = {}
        self._pending_tree_update = False

        self.uiq = UIQueue(self.root, fps=30)
        self.uiq.start()

        self.executor = SafeExecutor(max_workers=4)
        self.shutdown_mgr = ShutdownManager()
        self.telegram_controller = TelegramController(self)

        from ai.wom_engine import get_wom_engine
        from ai.ai_guardrail import get_guardrail

        self.wom_engine = get_wom_engine()
        self.guardrail = get_guardrail()

        from core.risk_middleware import RiskMiddleware
        from core.trading_engine import TradingEngine

        self.risk_middleware = RiskMiddleware(self.bus, self.guardrail, self.wom_engine)
        self.trading_engine = TradingEngine(
            self.bus, self.db, lambda: self.client, self.executor
        )

        def _feed_wom(payload):
            if not hasattr(self, "wom_engine") or not self.wom_engine:
                return
            for r in payload.get("runners_data", []):
                sel_id = r.get("selectionId")
                bp = r.get("backPrices", [])
                lp = r.get("layPrices", [])
                bp_price = bp[0][0] if bp else 0
                bp_vol = bp[0][1] if bp and len(bp[0]) > 1 else 0
                lp_price = lp[0][0] if lp else 0
                lp_vol = lp[0][1] if lp and len(lp[0]) > 1 else 0
                if sel_id and (bp_price > 0 or lp_price > 0):
                    self.wom_engine.record_tick(
                        sel_id, bp_price, bp_vol, lp_price, lp_vol
                    )

        self.bus.subscribe("MARKET_TICK", _feed_wom)

        self.bus.subscribe(
            "QUICK_BET_SUCCESS",
            lambda d: self.uiq.post(self._on_engine_success, d)
            if hasattr(self, "_on_engine_success")
            else None,
        )
        self.bus.subscribe(
            "QUICK_BET_FAILED",
            lambda e: self.uiq.post(self._on_engine_error, e)
            if hasattr(self, "_on_engine_error")
            else None,
        )
        self.bus.subscribe(
            "DUTCHING_SUCCESS",
            lambda d: self.uiq.post(self._on_engine_success, d)
            if hasattr(self, "_on_engine_success")
            else None,
        )
        self.bus.subscribe(
            "DUTCHING_FAILED",
            lambda e: self.uiq.post(self._on_engine_error, e)
            if hasattr(self, "_on_engine_error")
            else None,
        )
        self.bus.subscribe(
            "CASHOUT_SUCCESS",
            lambda d: self.uiq.post(self._on_cashout_success, d)
            if hasattr(self, "_on_cashout_success")
            else None,
        )
        self.bus.subscribe(
            "CASHOUT_FAILED",
            lambda e: self.uiq.post(self._on_cashout_failed, e)
            if hasattr(self, "_on_cashout_failed")
            else None,
        )

        if not hasattr(self, "last_ui_tick"):
            self.last_ui_tick = time.time()

        self.api_football = APIFootballClient(api_key="INSERISCI_TUA_API_KEY_QUI")
        self.goal_engine = GoalEnginePro(
            api_client=self.api_football,
            betfair_stream=getattr(self, "stream", None),
            hedge_callback=self._on_goal_hedge,
            reopen_callback=self._on_goal_reopen,
            ui_queue=self.uiq,
        )
        self.goal_engine.set_delay("500ms")
        self.goal_engine.set_confirm_mode(True)
        self.goal_engine.set_low_request_mode(True)
        self.goal_engine.start()

        self.shutdown_mgr.register("uiq", self.uiq.stop, priority=3)
        self.shutdown_mgr.register("goal_engine", self.goal_engine.stop, priority=5)
        if hasattr(self, "db") and self.db:
            self.shutdown_mgr.register("database", self.db.close, priority=4)

        from plugin_manager import PluginManager

        self.plugin_manager = PluginManager(self)
        self.plugin_tabs = {}

        self._create_menu()
        self._create_main_layout()

        self.tm_events = TreeManager(self.events_tree)
        self.tm_runners = TreeManager(self.runners_tree)
        self.tm_placed_bets = TreeManager(self.placed_bets_tree)
        self.tm_cashout = TreeManager(self.market_cashout_tree)

        self.root.after(3600000, self._schedule_order_cleanup)
        self._load_settings()
        self._configure_styles()

        if hasattr(self, "_start_booking_monitor"):
            self._start_booking_monitor()
        if hasattr(self, "_start_auto_cashout_monitor"):
            self._start_auto_cashout_monitor()
        self._check_for_updates_on_startup()

    def _create_telegram_tab(self):
        self.telegram_tab_ui = TelegramTabUI(self.telegram_tab, self)

    def _set_safe_mode(self, enabled, reason=None, source="SYSTEM"):
        enabled = bool(enabled)
        previous = getattr(self, "safe_mode_active", False)
        self.safe_mode_active = enabled

        payload = {
            "enabled": enabled,
            "reason": reason or "",
            "source": source,
            "ts": time.time(),
        }

        self.logger.warning(
            "SAFE MODE %s source=%s reason=%s",
            "ON" if enabled else "OFF",
            source,
            reason or "",
        )

        self.bus.publish("STATE_UPDATE_SAFE_MODE", payload)

        if previous != enabled:
            self.uiq.post(self._apply_safe_mode_ui, payload)

    def _on_safe_mode_trigger(self, data):
        data = data or {}
        reason = data.get("reason") or data.get("message") or "Trigger ricevuto"
        source = data.get("source") or "TRADING_ENGINE"
        self._set_safe_mode(True, reason=reason, source=source)

    def _apply_safe_mode_ui(self, payload):
        enabled = payload.get("enabled", False)
        reason = payload.get("reason", "")

        try:
            status_text = "SAFE MODE ATTIVO"
            if reason:
                status_text = f"{status_text} - {reason}"

            if hasattr(self, "status_label") and self.status_label.winfo_exists():
                self.status_label.configure(
                    text=status_text if enabled else "Safe Mode disattivato",
                    text_color=COLORS["warning"] if enabled else COLORS["success"],
                )
        except Exception:
            pass

        try:
            if hasattr(self, "place_btn") and self.place_btn.winfo_exists():
                self.place_btn.configure(state=ctk.DISABLED if enabled else ctk.NORMAL)
        except Exception:
            pass

        try:
            if hasattr(self, "dutch_modal_btn") and self.dutch_modal_btn.winfo_exists():
                self.dutch_modal_btn.configure(
                    state=ctk.DISABLED if enabled else ctk.NORMAL
                )
        except Exception:
            pass

        try:
            if hasattr(self, "connect_btn") and self.connect_btn.winfo_exists():
                self.connect_btn.configure(
                    fg_color=COLORS["warning"] if enabled else COLORS["button_primary"]
                )
        except Exception:
            pass

    def _buffer_market_tick(self, payload):
        market_id = payload["market_id"]
        if (
            not getattr(self, "current_market", None)
            or market_id != self.current_market["marketId"]
        ):
            return

        with self._buffer_lock:
            if len(self._market_update_buffer) > 5:
                self._market_update_buffer.clear()
            self._market_update_buffer[market_id] = payload["runners_data"]
            if not getattr(self, "_pending_tree_update", False):
                self._pending_tree_update = True
                self.root.after(100, self._throttled_refresh)

    def _throttled_refresh(self):
        with self._buffer_lock:
            snapshot = dict(self._market_update_buffer)
            self._market_update_buffer.clear()
            self._pending_tree_update = False

        if not getattr(self, "current_market", None):
            return
        market_id = self.current_market["marketId"]
        runners_data = snapshot.get(market_id)
        if not runners_data:
            return

        def update_ui():
            recalc_needed = False
            for runner_update in runners_data:
                selection_id = str(runner_update["selectionId"])
                try:
                    item = self.runners_tree.item(selection_id)
                    if not item:
                        continue
                    current_values = list(item["values"])
                    back_prices = runner_update.get("backPrices", [])
                    lay_prices = runner_update.get("layPrices", [])

                    if back_prices:
                        current_values[2] = f"{back_prices[0][0]:.2f}"
                        current_values[3] = (
                            f"{back_prices[0][1]:.0f}"
                            if len(back_prices[0]) > 1
                            else "-"
                        )
                    if lay_prices:
                        current_values[4] = f"{lay_prices[0][0]:.2f}"
                        current_values[5] = (
                            f"{lay_prices[0][1]:.0f}"
                            if len(lay_prices[0]) > 1
                            else "-"
                        )

                    self.runners_tree.item(selection_id, values=current_values)

                    if selection_id in self.selected_runners:
                        recalc_needed = True
                        if back_prices:
                            self.selected_runners[selection_id]["backPrice"] = back_prices[0][0]
                        if lay_prices:
                            self.selected_runners[selection_id]["layPrice"] = lay_prices[0][0]
                        bet_type = getattr(self, "bet_type_var", None)
                        if bet_type:
                            if bet_type.get() == "BACK" and back_prices:
                                self.selected_runners[selection_id]["price"] = back_prices[0][0]
                            elif bet_type.get() == "LAY" and lay_prices:
                                self.selected_runners[selection_id]["price"] = lay_prices[0][0]
                except Exception:
                    pass
            if recalc_needed:
                self._recalculate()

        self.uiq.post(update_ui)


if __name__ == "__main__":
    app = PickfairApp()
    app.root.mainloop()

