"""
Betfair Dutching - Tutti i Mercati
Main application orchestrator.
"""

import tkinter as tk
import customtkinter as ctk
import threading
import time

# Event Bus & Modules
from core.event_bus import EventBus
from app_modules.telegram_module import TelegramModule
from app_modules.streaming_module import StreamingModule
from app_modules.ui_module import UIModule
from app_modules.betting_module import BettingModule
from app_modules.simulation_module import SimulationModule
from app_modules.monitoring_module import MonitoringModule

# Dependencies
from database import Database
from telegram_listener import SignalQueue
from theme import COLORS
from ui_queue import UIQueue
from executor_manager import SafeExecutor
from shutdown_manager import ShutdownManager
from goal_engine_pro import APIFootballClient, GoalEnginePro
from tree_manager import TreeManager
from ui.tabs.telegram_tab_ui import TelegramTabUI
from controllers.telegram_controller import TelegramController

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
    MonitoringModule
):
    def __init__(self):
        from theme import configure_customtkinter
        configure_customtkinter()
        
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.configure(fg_color=COLORS['bg_dark'])
        
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
        
        self.db = Database()
        print(f"[DEBUG] Database path: {self.db.db_path}")

        # --- SISTEMA NERVOSO CENTRALE ---
        self.bus = EventBus()
        # Nota: handle_telegram_signal non era in temp_app.py. Se ce l'hai locale, il bus funzionerà. 
        if hasattr(self, '_handle_telegram_signal'):
            self.bus.subscribe("TELEGRAM_SIGNAL", self._handle_telegram_signal)
        
        self.bus.subscribe(
            "TELEGRAM_STATUS",
            lambda data: self._update_telegram_status(data['status'], data['message']) if hasattr(self, '_update_telegram_status') else None
        )
        # --------------------------------

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
        self.account_data = {'available': 0, 'exposure': 0, 'total': 0}
        self.telegram_listener = None
        self.telegram_signal_queue = SignalQueue()
        self.telegram_status = 'STOPPED'
        self.market_status = 'OPEN'
        self.simulation_mode = False
        
        self._buffer_lock = threading.Lock()
        self._market_update_buffer = {}
        self._pending_tree_update = False
        
        self.uiq = UIQueue(self.root, fps=30)
        self.uiq.start()
        
        self.executor = SafeExecutor(max_workers=4)
        self.shutdown_mgr = ShutdownManager()

        self.telegram_controller = TelegramController(self)
        
        if not hasattr(self, 'last_ui_tick'):
            self.last_ui_tick = time.time()
            # self._heartbeat() e self._freeze_guard() omesse qui perché non presenti nel tuo temp_app.py
            # Se le hai nel tuo main originario, puoi incollarle in un mixin (es: MonitoringModule)
        
        self.api_football = APIFootballClient(api_key="INSERISCI_TUA_API_KEY_QUI")
        self.goal_engine = GoalEnginePro(
            api_client=self.api_football,
            betfair_stream=getattr(self, 'stream', None),
            hedge_callback=self._on_goal_hedge,
            reopen_callback=self._on_goal_reopen,
            ui_queue=self.uiq
        )
        self.goal_engine.set_delay("500ms")
        self.goal_engine.set_confirm_mode(True)
        self.goal_engine.set_low_request_mode(True)
        self.goal_engine.start()
        
        self.shutdown_mgr.register("uiq", self.uiq.stop, priority=3)
        self.shutdown_mgr.register("goal_engine", self.goal_engine.stop, priority=5)
        if hasattr(self, 'db') and self.db:
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
        
        if hasattr(self, '_start_booking_monitor'): self._start_booking_monitor()
        if hasattr(self, '_start_auto_cashout_monitor'): self._start_auto_cashout_monitor()
        self._check_for_updates_on_startup()

    def _create_telegram_tab(self):
        """Delega costruzione UI Telegram a modulo esterno."""
        self.telegram_tab_ui = TelegramTabUI(self.telegram_tab, self)

if __name__ == "__main__":
    app = PickfairApp()
    app.root.mainloop()
