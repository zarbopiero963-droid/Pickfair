"""
Betfair Dutching - Tutti i Mercati
Main application with CustomTkinter GUI for Windows desktop.
Supports all market types and Streaming API for real-time prices.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import customtkinter as ctk
import threading
import json
from datetime import datetime

from database import Database
from betfair_client import BetfairClient, MARKET_TYPES
from dutching import calculate_dutching_stakes, validate_selections, format_currency
from telegram_listener import TelegramListener, SignalQueue
from auto_updater import check_for_updates, show_update_dialog, DEFAULT_UPDATE_URL
from theme import COLORS, FONTS, configure_customtkinter, configure_ttk_dark_theme
from plugin_manager import PluginManager, PluginAPI, PluginInfo
from dutching_ui import open_dutching_window

# --- HEDGE-FUND STABLE FIX ---
from ui_queue import UIQueue
from executor_manager import SafeExecutor
from shutdown_manager import ShutdownManager
from goal_engine_pro import APIFootballClient, GoalEnginePro
from tree_manager import TreeManager
# -----------------------------

APP_NAME = "Pickfair"
APP_VERSION = "3.19.1"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
LIVE_REFRESH_INTERVAL = 5000  # 5 seconds for live odds


class PickfairApp:
    def __init__(self):
        configure_customtkinter()
        
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.configure(fg_color=COLORS['bg_dark'])
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        taskbar_offset = 50
        available_height = screen_height - taskbar_offset
        
        window_width = min(WINDOW_WIDTH, int(screen_width * 0.9))
        window_height = min(WINDOW_HEIGHT, int(available_height * 0.9))
        
        x = (screen_width - window_width) // 2
        y = max(0, (available_height - window_height) // 2)
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        min_width = min(900, screen_width - 100)
        min_height = min(500, available_height - 50)
        self.root.minsize(min_width, min_height)
        
        self.root.resizable(True, True)
        
        if screen_width <= 1366 or screen_height <= 768:
            self.root.after(100, lambda: self._try_maximize())
        
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        self.db = Database()
        print(f"[DEBUG] Database path: {self.db.db_path}")
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
        self.simulation_mode = False  # Simulation mode flag
        
        # --- HEDGE-FUND STABLE FIX ---
        self._buffer_lock = threading.Lock()
        self._market_update_buffer = {}
        self._pending_tree_update = False
        
        # 1. Start UI Queue to process threaded UI updates safely
        self.uiq = UIQueue(self.root, fps=30)
        self.uiq.start()
        
        # 2. Thread Executor for API calls timeout protections
        self.executor = SafeExecutor(max_workers=4)
        self.shutdown_mgr = ShutdownManager()
        
        # 3. Goal Engine Pro (Anti-freeze/Anti-Double-Trigger)
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
        
        # 4. Register safe shutdowns to avoid SQLite WAL locks
        self.shutdown_mgr.register("uiq", self.uiq.stop, priority=3)
        self.shutdown_mgr.register("goal_engine", self.goal_engine.stop, priority=5)
        if hasattr(self, 'db') and self.db:
            self.shutdown_mgr.register("database", self.db.close, priority=4)
        # -----------------------------
        
        # Plugin system
        self.plugin_manager = PluginManager(self)
        self.plugin_tabs = {}  # Plugin-added tabs {name: (frame, plugin_name)}
        
        self._create_menu()
        self._create_main_layout()
        
        # --- HEDGE-FUND STABLE FIX: TREE MANAGERS ---
        self.tm_events = TreeManager(self.events_tree)
        self.tm_runners = TreeManager(self.runners_tree)
        self.tm_placed_bets = TreeManager(self.placed_bets_tree)
        self.tm_cashout = TreeManager(self.market_cashout_tree)
        
        # Schedule order cleanup
        self.root.after(3600000, self._schedule_order_cleanup)
        # --------------------------------------------
        
        self._load_settings()
        self._configure_styles()
        self._start_booking_monitor()
        self._start_auto_cashout_monitor()
        self._check_for_updates_on_startup()

    # --- HEDGE-FUND STABLE FIX: SCHEDULER & CALLBACKS ---
    def _schedule_order_cleanup(self):
        try:
            if hasattr(self, "order_manager") and self.order_manager:
                self.order_manager.cleanup_old(max_age_seconds=3600)
        except:
            pass
        self.root.after(3600000, self._schedule_order_cleanup)

    def _on_goal_hedge(self, match_id):
        import logging
        logging.getLogger("PickfairApp").info(f"HEDGE START match={match_id}")
        if hasattr(self, 'trading_engine'):
            pass

    def _on_goal_reopen(self, match_id):
        import logging
        logging.getLogger("PickfairApp").info(f"REOPEN positions match={match_id}")
        if hasattr(self, 'trading_engine'):
            pass
    # ----------------------------------------------------
    
    def _try_maximize(self):
        """Try to maximize window on Windows."""
        try:
            self.root.state('zoomed')
        except:
            pass
    
    def _configure_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        configure_ttk_dark_theme(style)
    
    def _create_menu(self):
        """Create application menu."""
        menubar = tk.Menu(self.root)
        self.root.configure(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Configura Credenziali", command=self._show_credentials_dialog)
        file_menu.add_command(label="Configura Aggiornamenti", command=self._show_update_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Verifica Aggiornamenti", command=self._check_for_updates_manual)
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self._on_close)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Strumenti", menu=tools_menu)
        tools_menu.add_command(label="Multi-Market Monitor", command=self._show_multi_market_monitor)
        tools_menu.add_command(label="Filtri Avanzati", command=self._show_advanced_filters)
        tools_menu.add_separator()
        tools_menu.add_command(label="Dashboard Simulazione", command=self._show_simulation_dashboard)
        tools_menu.add_command(label="Reset Simulazione", command=self._reset_simulation)
        
        telegram_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Telegram", menu=telegram_menu)
        telegram_menu.add_command(label="Configura Telegram", command=self._show_telegram_settings)
        telegram_menu.add_command(label="Segnali Ricevuti", command=self._show_telegram_signals)
        telegram_menu.add_separator()
        telegram_menu.add_command(label="Avvia Listener", command=self._start_telegram_listener)
        telegram_menu.add_command(label="Ferma Listener", command=self._stop_telegram_listener)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aiuto", menu=help_menu)
        help_menu.add_command(label="Informazioni", command=self._show_about)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _on_close(self):
        """Handle window close - with graceful shutdown logic."""
        self._stop_auto_refresh()
        
        try:
            if self.telegram_listener:
                self.telegram_listener.stop()
            self.shutdown_mgr.shutdown()
        except:
            pass
        
        if self.client:
            try: self.client.logout()
            except: pass
            
        self.root.destroy()
        import sys
        sys.exit(0)
    
    def _create_main_layout(self):
        """Create main application layout with tabs."""
        self.main_frame = ctk.CTkFrame(self.root, fg_color=COLORS['bg_dark'])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._create_status_bar()
        
        self.main_notebook = ctk.CTkTabview(self.main_frame, 
                                            fg_color=COLORS['bg_surface'],
                                            segmented_button_fg_color=COLORS['bg_panel'],
                                            segmented_button_selected_color=COLORS['back'],
                                            segmented_button_unselected_color=COLORS['bg_panel'],
                                            text_color=COLORS['text_primary'])
        self.main_notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.main_notebook.add("Trading")
        self.main_notebook.add("Dashboard")
        self.main_notebook.add("Telegram")
        self.main_notebook.add("Strumenti")
        self.main_notebook.add("Plugin")
        self.main_notebook.add("Impostazioni")
        self.main_notebook.add("Simulazione")
        
        self.trading_tab = self.main_notebook.tab("Trading")
        self.dashboard_tab = self.main_notebook.tab("Dashboard")
        self.telegram_tab = self.main_notebook.tab("Telegram")
        self.strumenti_tab = self.main_notebook.tab("Strumenti")
        self.plugin_tab = self.main_notebook.tab("Plugin")
        self.impostazioni_tab = self.main_notebook.tab("Impostazioni")
        self.simulazione_tab = self.main_notebook.tab("Simulazione")
        
        self._create_events_panel(self.trading_tab)
        self._create_market_panel(self.trading_tab)
        self._create_dutching_panel(self.trading_tab)
        
        self._create_dashboard_tab()
        self._create_telegram_tab()
        self._create_strumenti_tab()
        self._create_plugin_tab()
        self._create_impostazioni_tab()
        self._create_simulazione_tab()
    
    def _create_status_bar(self):
        """Create status bar with connection info and mode buttons."""
        status_frame = ctk.CTkFrame(self.main_frame, fg_color=COLORS['bg_panel'], corner_radius=8, height=50)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        status_frame.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(status_frame, text="Non connesso", 
                                         text_color=COLORS['error'], font=FONTS['default'])
        self.status_label.pack(side=tk.LEFT, padx=15)
        
        self.balance_label = ctk.CTkLabel(status_frame, text="", 
                                          text_color=COLORS['back'], font=('Segoe UI', 12, 'bold'))
        self.balance_label.pack(side=tk.LEFT, padx=20)
        
        self.stream_label = ctk.CTkLabel(status_frame, text="", 
                                         text_color=COLORS['warning'], font=FONTS['default'])
        self.stream_label.pack(side=tk.LEFT, padx=10)
        
        self.connect_btn = ctk.CTkButton(status_frame, text="Connetti", 
                                         command=self._toggle_connection,
                                         fg_color=COLORS['button_primary'],
                                         hover_color=COLORS['back_hover'],
                                         corner_radius=6, width=100)
        self.connect_btn.pack(side=tk.RIGHT, padx=10)
        
        self.refresh_btn = ctk.CTkButton(status_frame, text="Aggiorna", 
                                         command=self._refresh_data, state=tk.DISABLED,
                                         fg_color=COLORS['button_secondary'],
                                         hover_color=COLORS['back_hover'],
                                         corner_radius=6, width=100)
        self.refresh_btn.pack(side=tk.RIGHT, padx=5)
        
        self.live_btn = ctk.CTkButton(status_frame, text="LIVE",
                                      fg_color=COLORS['loss'], hover_color='#c62828',
                                      command=self._toggle_live_mode,
                                      corner_radius=6, width=80)
        self.live_btn.pack(side=tk.RIGHT, padx=5)
        
        self.sim_btn = ctk.CTkButton(status_frame, text="SIMULAZIONE",
                                     fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                                     command=self._toggle_simulation_mode,
                                     corner_radius=6, width=120)
        self.sim_btn.pack(side=tk.RIGHT, padx=5)
        
        self.sim_balance_label = ctk.CTkLabel(status_frame, text="", 
                                              text_color='#9c27b0', font=('Segoe UI', 11, 'bold'))
        self.sim_balance_label.pack(side=tk.LEFT, padx=10)
    
    def _create_events_panel(self, parent):
        """Create events list panel with country grouping."""
        events_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_panel'], corner_radius=8)
        events_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ctk.CTkLabel(events_frame, text="Partite", font=FONTS['heading'], 
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        search_frame = ctk.CTkFrame(events_frame, fg_color='transparent')
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._filter_events)
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, 
                                    placeholder_text="Cerca partita...",
                                    fg_color=COLORS['bg_card'], border_color=COLORS['border'])
        search_entry.pack(fill=tk.X)
        
        auto_refresh_frame = ctk.CTkFrame(events_frame, fg_color='transparent')
        auto_refresh_frame.pack(fill=tk.X, padx=10, pady=(5, 5))
        
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.auto_refresh_check = ctk.CTkCheckBox(
            auto_refresh_frame,
            text="Auto-refresh ogni",
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh,
            fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
            text_color=COLORS['text_primary']
        )
        self.auto_refresh_check.pack(side=tk.LEFT)
        
        self.auto_refresh_interval_var = tk.StringVar(value="30")
        self.auto_refresh_interval = ctk.CTkOptionMenu(
            auto_refresh_frame,
            variable=self.auto_refresh_interval_var,
            values=["15", "30", "60", "120", "300"],
            width=60,
            fg_color=COLORS['bg_card'], button_color=COLORS['back'],
            button_hover_color=COLORS['back_hover'],
            command=lambda v: self._on_auto_refresh_interval_change(None)
        )
        self.auto_refresh_interval.pack(side=tk.LEFT, padx=5)
        
        ctk.CTkLabel(auto_refresh_frame, text="sec", text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        
        self.auto_refresh_status = ctk.CTkLabel(auto_refresh_frame, text="", text_color=COLORS['success'])
        self.auto_refresh_status.pack(side=tk.LEFT, padx=10)
        
        tree_container = ctk.CTkFrame(events_frame, fg_color='transparent')
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        columns = ('name', 'date')
        self.events_tree = ttk.Treeview(tree_container, columns=columns, show='tree headings', height=20)
        self.events_tree.heading('#0', text='Nazione')
        self.events_tree.heading('name', text='Partita')
        self.events_tree.heading('date', text='Data')
        self.events_tree.column('#0', width=80, minwidth=60)
        self.events_tree.column('name', width=150, minwidth=100)
        self.events_tree.column('date', width=70, minwidth=60)
        
        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.events_tree.yview)
        self.events_tree.configure(yscrollcommand=scrollbar.set)
        
        self.events_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.events_tree.bind('<<TreeviewSelect>>', self._on_event_selected)
        
        self.all_events = []
        self.auto_refresh_id = None
    
    def _create_market_panel(self, parent):
        """Create market/runners panel with market type selector."""
        market_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_panel'], corner_radius=8)
        market_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ctk.CTkLabel(market_frame, text="Mercato", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        header_frame = ctk.CTkFrame(market_frame, fg_color='transparent')
        header_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.event_name_label = ctk.CTkLabel(header_frame, text="Seleziona una partita", 
                                             font=('Segoe UI', 12, 'bold'),
                                             text_color=COLORS['text_primary'])
        self.event_name_label.pack(anchor=tk.W)
        
        selector_frame = ctk.CTkFrame(market_frame, fg_color='transparent')
        selector_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(selector_frame, text="Tipo Mercato:", text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        self.market_type_var = tk.StringVar()
        self.market_combo = ctk.CTkOptionMenu(
            selector_frame, 
            variable=self.market_type_var,
            values=[""],
            width=200,
            fg_color=COLORS['bg_card'], button_color=COLORS['back'],
            button_hover_color=COLORS['back_hover'],
            command=lambda v: self._on_market_type_selected(None)
        )
        self.market_combo.pack(side=tk.LEFT, padx=5)
        
        stream_frame = ctk.CTkFrame(market_frame, fg_color='transparent')
        stream_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stream_var = tk.BooleanVar(value=False)
        self.stream_check = ctk.CTkCheckBox(
            stream_frame, 
            text="Streaming Quote Live", 
            variable=self.stream_var,
            command=self._toggle_streaming,
            fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
            text_color=COLORS['text_primary']
        )
        self.stream_check.pack(side=tk.LEFT)
        
        self.dutch_modal_btn = ctk.CTkButton(
            stream_frame, 
            text="Dutching Avanzato", 
            fg_color=COLORS['info'], hover_color=COLORS['info_hover'],
            command=self._show_dutching_modal,
            state=tk.DISABLED,
            corner_radius=6, width=130
        )
        self.dutch_modal_btn.pack(side=tk.LEFT, padx=5)
        
        self.market_status_label = ctk.CTkLabel(
            stream_frame,
            text="",
            font=('Segoe UI', 9, 'bold')
        )
        self.market_status_label.pack(side=tk.RIGHT, padx=10)
        
        runners_container = ctk.CTkFrame(market_frame, fg_color='transparent')
        runners_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        columns = ('select', 'name', 'back', 'back_size', 'lay', 'lay_size')
        self.runners_tree = ttk.Treeview(runners_container, columns=columns, show='headings', height=18)
        self.runners_tree.heading('select', text='')
        self.runners_tree.heading('name', text='Selezione')
        self.runners_tree.heading('back', text='Back')
        self.runners_tree.heading('back_size', text='Disp.')
        self.runners_tree.heading('lay', text='Lay')
        self.runners_tree.heading('lay_size', text='Disp.')
        self.runners_tree.column('select', width=30)
        self.runners_tree.column('name', width=120)
        self.runners_tree.column('back', width=60)
        self.runners_tree.column('back_size', width=60)
        self.runners_tree.column('lay', width=60)
        self.runners_tree.column('lay_size', width=60)
        
        self.runners_tree.tag_configure('runner_row', background=COLORS['bg_card'])
        
        scrollbar = ttk.Scrollbar(runners_container, orient=tk.VERTICAL, command=self.runners_tree.yview)
        self.runners_tree.configure(yscrollcommand=scrollbar.set)
        
        self.runners_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.runners_tree.bind('<ButtonRelease-1>', self._on_runner_clicked)
        self.runners_tree.bind('<Button-3>', self._show_runner_context_menu)
        
        self.runners_tree.tag_configure('clickable_back', foreground=COLORS['clickable_back'])
        self.runners_tree.tag_configure('clickable_lay', foreground=COLORS['clickable_lay'])
        
        self.runner_context_menu = tk.Menu(self.root, tearoff=0)
        self.runner_context_menu.add_command(label="Prenota Scommessa", command=self._book_selected_runner)
        self.runner_context_menu.add_separator()
        self.runner_context_menu.add_command(label="Seleziona per Dutching", command=lambda: None)
    
    def _create_dutching_panel(self, parent):
        """Create dutching calculator panel with scrollable content."""
        dutch_outer = ctk.CTkFrame(parent, fg_color=COLORS['bg_panel'], corner_radius=8)
        dutch_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        ctk.CTkLabel(dutch_outer, text="Calcolo Dutching", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        canvas = tk.Canvas(dutch_outer, highlightthickness=0, bg=COLORS['bg_panel'])
        scrollbar = ttk.Scrollbar(dutch_outer, orient=tk.VERTICAL, command=canvas.yview)
        dutch_frame = ctk.CTkFrame(canvas, fg_color='transparent')
        
        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        dutch_frame.bind('<Configure>', configure_scroll)
        canvas_window = canvas.create_window((0, 0), window=dutch_frame, anchor='nw')
        
        def configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def bind_mousewheel(event):
            canvas.bind_all('<MouseWheel>', on_mousewheel)
        
        def unbind_mousewheel(event):
            canvas.unbind_all('<MouseWheel>')
        
        canvas.bind('<Enter>', bind_mousewheel)
        canvas.bind('<Leave>', unbind_mousewheel)
        dutch_frame.bind('<Enter>', bind_mousewheel)
        dutch_frame.bind('<Leave>', unbind_mousewheel)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        type_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        type_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(type_frame, text="Tipo:", text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        self.bet_type_var = tk.StringVar(value='BACK')
        
        self.back_btn = ctk.CTkButton(type_frame, text="Back", 
                                      fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                                      corner_radius=6, width=80,
                                      command=lambda: self._set_bet_type('BACK'))
        self.back_btn.pack(side=tk.LEFT, padx=5)
        
        self.lay_btn = ctk.CTkButton(type_frame, text="Lay", 
                                     fg_color=COLORS['lay'], hover_color=COLORS['lay_hover'],
                                     corner_radius=6, width=80,
                                     command=lambda: self._set_bet_type('LAY'))
        self.lay_btn.pack(side=tk.LEFT)
        
        stake_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        stake_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ctk.CTkLabel(stake_frame, text="Stake Totale (EUR):", text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        self.stake_var = tk.StringVar(value='1.00')
        self.stake_var.trace_add('write', lambda *args: self._recalculate())
        stake_entry = ctk.CTkEntry(stake_frame, textvariable=self.stake_var, width=80,
                                   fg_color=COLORS['bg_card'], border_color=COLORS['border'])
        stake_entry.pack(side=tk.LEFT, padx=5)
        
        ctk.CTkLabel(stake_frame, text="(min. 1 EUR per selezione)", 
                     font=('Segoe UI', 8), text_color=COLORS['text_tertiary']).pack(side=tk.LEFT, padx=5)
        
        options_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        options_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.best_price_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(options_frame, text="Accetta Miglior Prezzo", 
                        variable=self.best_price_var,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary']).pack(side=tk.LEFT)
        ctk.CTkLabel(options_frame, text="(piazza al prezzo corrente)", 
                     font=('Segoe UI', 8), text_color=COLORS['text_tertiary']).pack(side=tk.LEFT, padx=5)
        
        ctk.CTkLabel(dutch_frame, text="Selezioni:", font=('Segoe UI', 11, 'bold'),
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        self.selections_text = ctk.CTkTextbox(dutch_frame, height=100, 
                                               fg_color=COLORS['bg_card'], 
                                               text_color=COLORS['text_primary'],
                                               border_color=COLORS['border'])
        self.selections_text.pack(fill=tk.BOTH, expand=True, padx=10)
        self.selections_text.configure(state=tk.DISABLED)
        
        ctk.CTkLabel(dutch_frame, text="Scommesse Piazzate:", font=('Segoe UI', 11, 'bold'),
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 2))
        
        placed_cols = ('sel', 'tipo', 'quota', 'stake')
        self.placed_bets_tree = ttk.Treeview(dutch_frame, columns=placed_cols, show='headings', height=4)
        self.placed_bets_tree.heading('sel', text='Selezione')
        self.placed_bets_tree.heading('tipo', text='Tipo')
        self.placed_bets_tree.heading('quota', text='Quota')
        self.placed_bets_tree.heading('stake', text='Stake')
        self.placed_bets_tree.column('sel', width=100)
        self.placed_bets_tree.column('tipo', width=40)
        self.placed_bets_tree.column('quota', width=50)
        self.placed_bets_tree.column('stake', width=50)
        
        self.placed_bets_tree.tag_configure('back', foreground=COLORS['back'])
        self.placed_bets_tree.tag_configure('lay', foreground=COLORS['lay'])
        
        self.placed_bets_tree.pack(fill=tk.X, padx=10, pady=2)
        
        summary_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        summary_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.profit_label = ctk.CTkLabel(summary_frame, text="Profitto: -", 
                                         font=('Segoe UI', 11, 'bold'),
                                         text_color=COLORS['text_primary'])
        self.profit_label.pack(anchor=tk.W)
        
        self.prob_label = ctk.CTkLabel(summary_frame, text="Probabilita Implicita: -",
                                       text_color=COLORS['text_secondary'])
        self.prob_label.pack(anchor=tk.W)
        
        btn_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ctk.CTkButton(btn_frame, text="Cancella Selezioni", command=self._clear_selections,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6).pack(side=tk.LEFT)
        
        ctk.CTkButton(btn_frame, text="Dutching Pro", command=self._open_dutching_window,
                      fg_color=COLORS['info'], hover_color=COLORS['info_hover'],
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=10)
        
        self.place_btn = ctk.CTkButton(btn_frame, text="Piazza Scommesse", command=self._place_bets, 
                                       state=tk.DISABLED,
                                       fg_color=COLORS['button_success'], hover_color='#4caf50',
                                       corner_radius=6)
        self.place_btn.pack(side=tk.RIGHT)
        
        separator = ctk.CTkFrame(dutch_frame, fg_color=COLORS['border'], height=2)
        separator.pack(fill=tk.X, padx=10, pady=10)
        
        ctk.CTkLabel(dutch_frame, text="Cashout", font=('Segoe UI', 11, 'bold'),
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(5, 2))
        
        cashout_cols = ('sel', 'tipo', 'p/l')
        self.market_cashout_tree = ttk.Treeview(dutch_frame, columns=cashout_cols, show='headings', height=4)
        self.market_cashout_tree.heading('sel', text='Selezione')
        self.market_cashout_tree.heading('tipo', text='Tipo')
        self.market_cashout_tree.heading('p/l', text='P/L')
        self.market_cashout_tree.column('sel', width=80)
        self.market_cashout_tree.column('tipo', width=40)
        self.market_cashout_tree.column('p/l', width=60)
        
        self.market_cashout_tree.tag_configure('profit', foreground=COLORS['success'])
        self.market_cashout_tree.tag_configure('loss', foreground=COLORS['loss'])
        
        self.market_cashout_tree.pack(fill=tk.X, padx=10, pady=2)
        
        cashout_btn_frame = ctk.CTkFrame(dutch_frame, fg_color='transparent')
        cashout_btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.market_cashout_btn = ctk.CTkButton(cashout_btn_frame, text="CASHOUT", 
                                                fg_color=COLORS['success'], hover_color='#0d9668',
                                                font=('Segoe UI', 9, 'bold'), state=tk.DISABLED,
                                                corner_radius=6, width=100,
                                                command=self._do_market_cashout)
        self.market_cashout_btn.pack(side=tk.LEFT, padx=2)
        
        self.auto_cashout_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(cashout_btn_frame, text="Auto", variable=self.auto_cashout_var,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary'], width=60).pack(side=tk.LEFT, padx=5)
        
        self.market_live_tracking_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(cashout_btn_frame, text="Live", variable=self.market_live_tracking_var,
                        command=self._toggle_market_live_tracking,
                        fg_color=COLORS['success'], hover_color='#4caf50',
                        text_color=COLORS['text_primary'], width=60).pack(side=tk.LEFT, padx=5)
        
        self.market_live_status = ctk.CTkLabel(cashout_btn_frame, text="", 
                                               font=('Segoe UI', 8, 'bold'),
                                               text_color=COLORS['text_secondary'])
        self.market_live_status.pack(side=tk.LEFT)
        
        ctk.CTkButton(cashout_btn_frame, text="Aggiorna", command=self._update_market_cashout_positions,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=80).pack(side=tk.RIGHT, padx=2)
        
        self.market_cashout_tree.bind('<Double-1>', self._do_single_cashout)
        
        self.market_live_tracking_id = None
        self.market_cashout_fetch_in_progress = False
        self.market_cashout_fetch_cancelled = False
        self.market_cashout_positions = {}
    
    def _update_placed_bets(self):
        """Update placed bets list for current market."""
        if not self.client or not self.current_market:
            return
        
        market_id = self.current_market.get('marketId')
        if not market_id:
            return
        
        runner_names = {}
        for runner in self.current_market.get('runners', []):
            runner_names[runner['selectionId']] = runner['runnerName']
        
        def fetch_bets():
            try:
                orders = self.client.get_current_orders()
                matched = orders.get('matched', [])
                market_orders = [o for o in matched if o.get('marketId') == market_id]
                self.uiq.post(self._display_placed_bets, market_orders, runner_names)
            except Exception as e:
                print(f"Error fetching placed bets: {e}")
        
        self.executor.submit("fetch_placed_bets", fetch_bets)
    
    def _display_placed_bets(self, orders, runner_names):
        """Display placed bets in treeview using TreeManager."""
        bets_data = []
        for order in orders:
            selection_id = order.get('selectionId')
            side = order.get('side', 'BACK')
            price = order.get('price', 0)
            stake = order.get('sizeMatched', 0)
            bet_id = order.get('betId')
            
            runner_name = runner_names.get(selection_id, f"ID:{selection_id}")
            if len(runner_name) > 15:
                runner_name = runner_name[:15] + "..."
            
            tag = 'back' if side == 'BACK' else 'lay'
            
            bets_data.append({
                'id': bet_id,
                'values': (runner_name, side[:1], f"{price:.2f}", f"{stake:.2f}"),
                'tags': (tag,)
            })
            
        self.tm_placed_bets.update_flat(
            data=bets_data,
            id_getter=lambda b: str(b['id']),
            values_getter=lambda b: b['values'],
            tags_getter=lambda b: b['tags']
        )
    
    def _update_market_cashout_positions(self):
        """Update cashout positions for current market."""
        if self.market_cashout_fetch_in_progress:
            return
        
        if not self.client or not self.current_market:
            self.market_cashout_btn.configure(state=tk.DISABLED)
            return
        
        market_id = self.current_market.get('marketId')
        if not market_id:
            return
        
        self.market_cashout_fetch_in_progress = True
        self.market_cashout_fetch_cancelled = False
        
        current_market_id = market_id
        
        def fetch_positions():
            try:
                if self.market_cashout_fetch_cancelled:
                    self.market_cashout_fetch_in_progress = False
                    return
                
                orders = self.client.get_current_orders()
                matched = orders.get('matched', [])
                
                if self.market_cashout_fetch_cancelled:
                    self.market_cashout_fetch_in_progress = False
                    return
                
                market_orders = [o for o in matched if o.get('marketId') == current_market_id]
                
                positions = []
                for order in market_orders:
                    if self.market_cashout_fetch_cancelled:
                        self.market_cashout_fetch_in_progress = False
                        return
                    
                    selection_id = order.get('selectionId')
                    side = order.get('side')
                    price = order.get('price', 0)
                    stake = order.get('sizeMatched', 0)
                    
                    if stake > 0:
                        try:
                            cashout_info = self.client.calculate_cashout(
                                current_market_id, selection_id, side, stake, price
                            )
                            green_up = cashout_info.get('green_up', 0)
                        except:
                            cashout_info = None
                            green_up = 0
                        
                        runner_name = str(selection_id)
                        if self.current_market and self.current_market.get('marketId') == current_market_id:
                            for r in self.current_market.get('runners', []):
                                if str(r.get('selectionId')) == str(selection_id):
                                    runner_name = r.get('runnerName', runner_name)[:15]
                                    break
                        
                        positions.append({
                            'bet_id': order.get('betId'),
                            'selection_id': selection_id,
                            'runner_name': runner_name,
                            'side': side,
                            'price': price,
                            'stake': stake,
                            'green_up': green_up,
                            'cashout_info': cashout_info
                        })
                
                def update_ui():
                    self.market_cashout_fetch_in_progress = False
                    if not self.market_cashout_fetch_cancelled:
                        if self.current_market and self.current_market.get('marketId') == current_market_id:
                            self._display_market_cashout_positions(positions)
                
                self.uiq.post(update_ui)
            except Exception as e:
                self.market_cashout_fetch_in_progress = False
                print(f"Error fetching cashout positions: {e}")
        
        self.executor.submit("fetch_cashout", fetch_positions)
    
    def _display_market_cashout_positions(self, positions):
        """Display cashout positions in market view using TreeManager."""
        self.market_cashout_positions = {}
        cashout_data = []
        
        for pos in positions:
            bet_id = pos['bet_id']
            green_up = pos['green_up']
            pl_tag = 'profit' if green_up > 0 else 'loss'
            
            self.market_cashout_positions[str(bet_id)] = pos
            
            cashout_data.append({
                'id': bet_id,
                'values': (pos['runner_name'], pos['side'], f"{green_up:+.2f}"),
                'tags': (pl_tag,)
            })
            
        self.tm_cashout.update_flat(
            data=cashout_data,
            id_getter=lambda c: str(c['id']),
            values_getter=lambda c: c['values'],
            tags_getter=lambda c: c['tags']
        )
        
        if positions:
            self.market_cashout_btn.configure(state=tk.NORMAL)
        else:
            self.market_cashout_btn.configure(state=tk.DISABLED)
    
    def _toggle_market_live_tracking(self):
        """Toggle live tracking for market cashout."""
        if self.market_live_tracking_var.get():
            self._start_market_live_tracking()
        else:
            self._stop_market_live_tracking()
    
    def _start_market_live_tracking(self):
        """Start live tracking for market cashout."""
        def update():
            if not self.market_live_tracking_var.get():
                return
            self._update_market_cashout_positions()
            self.market_live_tracking_id = self.root.after(5000, update)
        
        self._update_market_cashout_positions()
        self.market_live_tracking_id = self.root.after(5000, update)
        self.market_live_status.configure(text="LIVE", text_color=COLORS['success'])
    
    def _stop_market_live_tracking(self):
        """Stop live tracking for market cashout."""
        if self.market_live_tracking_id:
            self.root.after_cancel(self.market_live_tracking_id)
            self.market_live_tracking_id = None
        self.market_cashout_fetch_cancelled = True
        self.market_live_status.configure(text="", text_color=COLORS['text_secondary'])
    
    def _do_single_cashout(self, event):
        """Execute cashout for double-clicked position."""
        item = self.market_cashout_tree.identify_row(event.y)
        if item:
            self.market_cashout_tree.selection_set(item)
            self._do_market_cashout()
    
    def _do_market_cashout(self):
        """Execute cashout for selected position in market view."""
        selected = self.market_cashout_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una posizione")
            return
        
        for bet_id in selected:
            pos = self.market_cashout_positions.get(bet_id)
            if not pos or not pos.get('cashout_info'):
                continue
            
            info = pos['cashout_info']
            
            if self.auto_cashout_var.get():
                confirm = True
            else:
                confirm = messagebox.askyesno(
                    "Conferma Cashout",
                    f"Eseguire cashout?\n\n"
                    f"Selezione: {pos['runner_name']}\n"
                    f"Tipo: {info['cashout_side']} @ {info['current_price']:.2f}\n"
                    f"Stake: {info['cashout_stake']:.2f}\n"
                    f"Profitto garantito: {info['green_up']:+.2f}"
                )
            
            if confirm:
                try:
                    result = self.client.execute_cashout(
                        self.current_market['marketId'],
                        pos['selection_id'],
                        info['cashout_side'],
                        info['cashout_stake'],
                        info['current_price']
                    )
                    
                    if result.get('status') == 'SUCCESS':
                        self.db.save_cashout_transaction(
                            market_id=self.current_market['marketId'],
                            selection_id=pos['selection_id'],
                            original_bet_id=bet_id,
                            cashout_bet_id=result.get('betId'),
                            original_side=pos['side'],
                            original_stake=pos['stake'],
                            original_price=pos['price'],
                            cashout_side=info['cashout_side'],
                            cashout_stake=info['cashout_stake'],
                            cashout_price=result.get('averagePriceMatched') or info['current_price'],
                            profit_loss=info['green_up']
                        )
                        messagebox.showinfo("Successo", f"Cashout eseguito!\nProfitto: {info['green_up']:+.2f}")
                        self._update_market_cashout_positions()
                        self._update_balance()
                    else:
                        messagebox.showerror("Errore", f"Cashout fallito: {result.get('error', 'Errore')}")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore cashout: {e}")
    
    def _load_settings(self):
        """Load saved settings."""
        settings = self.db.get_settings()
        if settings and settings.get('session_token'):
            self._try_restore_session(settings)
    
    def _try_restore_session(self, settings):
        """Try to restore previous session."""
        if not all([settings.get('username'), settings.get('app_key'), 
                   settings.get('certificate'), settings.get('private_key')]):
            return
        
        expiry = settings.get('session_expiry')
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry)
                if datetime.now() < expiry_dt:
                    self.status_label.configure(text="Sessione salvata (clicca Connetti)", text_color=COLORS['text_secondary'])
            except:
                pass
    
    def _show_credentials_dialog(self):
        """Show credentials configuration dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Credenziali Betfair")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        settings = self.db.get_settings() or {}
        
        ttk.Label(frame, text="Username Betfair:").pack(anchor=tk.W)
        username_var = tk.StringVar(value=settings.get('username', ''))
        ttk.Entry(frame, textvariable=username_var, width=50).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(frame, text="App Key:").pack(anchor=tk.W)
        appkey_var = tk.StringVar(value=settings.get('app_key', ''))
        ttk.Entry(frame, textvariable=appkey_var, width=50).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(frame, text="Certificato SSL (.pem):").pack(anchor=tk.W)
        cert_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        cert_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get('certificate'):
            cert_text.insert('1.0', settings['certificate'])
        
        def load_cert():
            path = filedialog.askopenfilename(filetypes=[
                ("Certificati", "*.pem *.crt *.cer"),
                ("PEM files", "*.pem"),
                ("CRT files", "*.crt"),
                ("All files", "*.*")
            ])
            if path:
                with open(path, 'r') as f:
                    cert_text.delete('1.0', tk.END)
                    cert_text.insert('1.0', f.read())
        
        ttk.Button(frame, text="Carica da file...", command=load_cert).pack(anchor=tk.W, pady=(0, 10))
        
        ttk.Label(frame, text="Chiave Privata (.key o .pem):").pack(anchor=tk.W)
        key_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        key_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get('private_key'):
            key_text.insert('1.0', settings['private_key'])
        
        def load_key():
            path = filedialog.askopenfilename(filetypes=[
                ("Chiavi private", "*.pem *.key"),
                ("PEM files", "*.pem"),
                ("KEY files", "*.key"),
                ("All files", "*.*")
            ])
            if path:
                with open(path, 'r') as f:
                    key_text.delete('1.0', tk.END)
                    key_text.insert('1.0', f.read())
        
        ttk.Button(frame, text="Carica da file...", command=load_key).pack(anchor=tk.W, pady=(0, 20))
        
        def save():
            self.db.save_credentials(
                username_var.get(),
                appkey_var.get(),
                cert_text.get('1.0', tk.END).strip(),
                key_text.get('1.0', tk.END).strip()
            )
            messagebox.showinfo("Salvato", "Credenziali salvate con successo!")
            dialog.destroy()
        
        ttk.Button(frame, text="Salva", command=save).pack(pady=10)
    
    def _toggle_connection(self):
        """Connect or disconnect from Betfair."""
        if self.client:
            self._disconnect()
        else:
            self._connect()
    
    def _connect(self):
        """Connect to Betfair."""
        settings = self.db.get_settings()
        
        if not all([settings.get('username'), settings.get('app_key'),
                   settings.get('certificate'), settings.get('private_key')]):
            messagebox.showerror("Errore", "Configura prima le credenziali dal menu File")
            return
        
        pwd_dialog = tk.Toplevel(self.root)
        pwd_dialog.title("Password Betfair")
        pwd_dialog.geometry("350x180")
        pwd_dialog.transient(self.root)
        pwd_dialog.grab_set()
        
        pwd_dialog.update_idletasks()
        x = (pwd_dialog.winfo_screenwidth() // 2) - (175)
        y = (pwd_dialog.winfo_screenheight() // 2) - (90)
        pwd_dialog.geometry(f"350x180+{x}+{y}")
        
        frame = ttk.Frame(pwd_dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Password Betfair:").pack(anchor=tk.W)
        
        saved_password = settings.get('password', '')
        pwd_var = tk.StringVar(value=saved_password or '')
        pwd_entry = ttk.Entry(frame, textvariable=pwd_var, show='*')
        pwd_entry.pack(fill=tk.X, pady=5)
        pwd_entry.focus()
        
        save_pwd_var = tk.BooleanVar(value=bool(saved_password))
        ttk.Checkbutton(frame, text="Salva Password", variable=save_pwd_var).pack(anchor=tk.W, pady=5)
        
        def do_login():
            password = pwd_var.get()
            
            if save_pwd_var.get():
                self.db.save_password(password)
            else:
                self.db.save_password(None)
            
            pwd_dialog.destroy()
            
            self.status_label.configure(text="Connessione in corso...", text_color=COLORS['text_secondary'])
            self.connect_btn.configure(state=tk.DISABLED)
            
            def login_thread():
                try:
                    self.client = BetfairClient(
                        settings['username'],
                        settings['app_key'],
                        settings['certificate'],
                        settings['private_key']
                    )
                    result = self.client.login(password)
                    
                    self.db.save_session(result['session_token'], result['expiry'])
                    
                    self.uiq.post(self._on_connected)
                except Exception as e:
                    error_msg = str(e)
                    self.uiq.post(self._on_connection_error, error_msg)
            
            self.executor.submit("login_task", login_thread)
        
        pwd_entry.bind('<Return>', lambda e: do_login())
        ttk.Button(frame, text="Connetti", command=do_login).pack(pady=10)
    
    def _on_connected(self):
        """Handle successful connection."""
        self.status_label.configure(text="Connesso a Betfair Italia", text_color=COLORS['success'])
        self.connect_btn.configure(text="Disconnetti", state=tk.NORMAL)
        self.refresh_btn.configure(state=tk.NORMAL)
        
        self._update_balance()
        self._load_events()
        
        self.auto_refresh_var.set(True)
        self._start_auto_refresh()
        
        self._start_session_keepalive()
        self._refresh_dashboard_tab()
    
    def _start_session_keepalive(self):
        """Start periodic session keep-alive to prevent timeout."""
        self.keepalive_id = None
        
        def keepalive():
            if self.client:
                try:
                    self.client.get_account_balance()
                except Exception as e:
                    print(f"Keepalive failed: {e}")
                    self._try_silent_relogin()
            
            if self.client:
                self.keepalive_id = self.root.after(600000, keepalive)
        
        self.keepalive_id = self.root.after(600000, keepalive)
    
    def _stop_session_keepalive(self):
        """Stop session keep-alive."""
        if hasattr(self, 'keepalive_id') and self.keepalive_id:
            self.root.after_cancel(self.keepalive_id)
            self.keepalive_id = None
    
    def _try_silent_relogin(self):
        """Try to re-login silently if session expired."""
        settings = self.db.get_settings()
        password = settings.get('password')
        
        if password and self.client:
            try:
                result = self.client.login(password)
                self.db.save_session(result['session_token'], result['expiry'])
                print("Session renewed successfully")
            except Exception as e:
                print(f"Silent relogin failed: {e}")
                self.uiq.post(messagebox.showwarning, "Sessione Scaduta", "La sessione è scaduta. Riconnettiti manualmente.")
    
    def _on_connection_error(self, error):
        """Handle connection error."""
        self.status_label.configure(text=f"Errore: {error}", text_color=COLORS['error'])
        self.connect_btn.configure(text="Connetti", state=tk.NORMAL)
        self.client = None
        messagebox.showerror("Errore Connessione", error)
    
    def _disconnect(self):
        """Disconnect from Betfair."""
        self._stop_auto_refresh()
        self._stop_session_keepalive()
        self.auto_refresh_var.set(False)
        
        if self.client:
            self.client.logout()
            self.client = None
        
        self.db.clear_session()
        self.status_label.configure(text="Non connesso", text_color=COLORS['error'])
        self.stream_label.configure(text="")
        self.connect_btn.configure(text="Connetti")
        self.refresh_btn.configure(state=tk.DISABLED)
        self.balance_label.configure(text="")
        self.streaming_active = False
        self.stream_var.set(False)
        
        self.events_tree.delete(*self.events_tree.get_children())
        self.runners_tree.delete(*self.runners_tree.get_children())
        self.market_combo['values'] = []
        self._clear_selections()
    
    def _update_balance(self):
        """Update account balance display."""
        def fetch():
            try:
                funds = self.client.get_account_funds()
                self.uiq.post(self.balance_label.configure, text=f"Saldo: {format_currency(funds['available'])}")
            except Exception as e:
                print(f"Error fetching balance: {e}")
        
        self.executor.submit("fetch_balance", fetch)
    
    def _load_events(self):
        """Load football events."""
        def fetch():
            try:
                events = self.client.get_football_events()
                self.uiq.post(self._display_events, events)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", f"Errore caricamento partite: {err_msg}")
        
        self.executor.submit("fetch_events", fetch)
    
    def _display_events(self, events):
        """Display events in treeview grouped by country using TreeManager."""
        self.all_events = events
        self._populate_events_tree()
    
    def _populate_events_tree(self):
        """Populate events tree based on current search filter using TreeManager."""
        search = self.search_var.get().lower()
        
        filtered_events = []
        if search:
            for event in self.all_events:
                if search in event['name'].lower():
                    filtered_events.append(event)
        else:
            filtered_events = self.all_events

        self.tm_events.update_hierarchical(
            data=filtered_events,
            parent_getter=lambda e: f"country_{e.get('countryCode', 'XX') or 'XX'}",
            id_getter=lambda e: e['id'],
            text_getter=lambda e: e.get('countryCode', 'XX') or 'XX',
            values_getter=lambda e: (e['name'], self._format_event_date(e))
        )
    
    def _format_event_date(self, event):
        """Format event date for display, with LIVE indicator for in-play events."""
        if event.get('inPlay'):
            return "LIVE"
        if event.get('openDate'):
            try:
                dt = datetime.fromisoformat(event['openDate'].replace('Z', '+00:00'))
                return dt.strftime('%d/%m %H:%M')
            except:
                return event['openDate'][:16]
        return ""
    
    def _filter_events(self, *args):
        """Filter events by search text."""
        self._populate_events_tree()
    
    def _toggle_auto_refresh(self):
        """Toggle auto-refresh of events list."""
        if self.auto_refresh_var.get():
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()
    
    def _start_auto_refresh(self):
        """Start auto-refresh timer (in seconds)."""
        if not self.client:
            self.auto_refresh_var.set(False)
            return
        
        self._stop_auto_refresh()
        
        interval_sec = int(self.auto_refresh_interval_var.get())
        interval_ms = interval_sec * 1000
        
        def do_refresh():
            if self.client and self.auto_refresh_var.get():
                self._load_events()
                self._update_balance()
                now = datetime.now().strftime('%H:%M:%S')
                self.auto_refresh_status.configure(text=f"Ultimo: {now}")
                self.auto_refresh_id = self.root.after(interval_ms, do_refresh)
        
        self.auto_refresh_id = self.root.after(interval_ms, do_refresh)
        self.auto_refresh_status.configure(text="Attivo")
    
    def _stop_auto_refresh(self):
        """Stop auto-refresh timer."""
        if self.auto_refresh_id:
            self.root.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None
        self.auto_refresh_status.configure(text="")
    
    def _on_auto_refresh_interval_change(self, event=None):
        """Handle auto-refresh interval change."""
        if self.auto_refresh_var.get():
            self._start_auto_refresh()
    
    def _refresh_data(self):
        """Refresh all data."""
        self._update_balance()
        self._load_events()
        if self.current_event:
            self._load_available_markets(self.current_event['id'])
    
    def _on_event_selected(self, event):
        """Handle event selection."""
        selection = self.events_tree.selection()
        if not selection:
            return
        
        event_id = selection[0]
        
        if event_id.startswith('country_'):
            return
        
        for evt in self.all_events:
            if evt['id'] == event_id:
                self.current_event = evt
                self.event_name_label.configure(text=evt['name'])
                break
        else:
            return
        
        self._stop_streaming()
        self._clear_selections()
        self._load_available_markets(event_id)
    
    def _load_available_markets(self, event_id):
        """Load all available markets for an event."""
        self.runners_tree.delete(*self.runners_tree.get_children())
        self.market_combo['values'] = []
        
        def fetch():
            try:
                markets = self.client.get_available_markets(event_id)
                self.uiq.post(self._display_available_markets, markets)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", f"Errore caricamento mercati: {err_msg}")
        
        self.executor.submit("fetch_markets", fetch)
    
    def _display_available_markets(self, markets):
        """Display available markets in dropdown."""
        self.available_markets = markets
        
        if not markets:
            self.market_combo['values'] = ["Nessun mercato disponibile"]
            return
        
        display_names = []
        for m in markets:
            name = m.get('displayName') or m.get('marketName', 'Sconosciuto')
            if m.get('inPlay'):
                name = f"[LIVE] {name}"
            display_names.append(name)
        
        self.market_combo['values'] = display_names
        
        if display_names:
            self.market_combo.current(0)
            self._on_market_type_selected(None)
    
    def _on_market_type_selected(self, event):
        """Handle market type selection from dropdown."""
        selection = self.market_combo.current()
        if selection < 0 or selection >= len(self.available_markets):
            return
        
        market = self.available_markets[selection]
        self._stop_streaming()
        self._clear_selections()
        self._load_market(market['marketId'])
    
    def _load_market(self, market_id):
        """Load a specific market with prices."""
        self.runners_tree.delete(*self.runners_tree.get_children())
        
        def fetch():
            try:
                market = self.client.get_market_with_prices(market_id)
                self.uiq.post(self._display_market, market)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", f"Mercato non disponibile: {err_msg}")
        
        self.executor.submit("fetch_market_prices", fetch)
    
    def _display_market(self, market):
        """Display market runners using TreeManager."""
        self.current_market = market
        
        self.market_status = market.get('status', 'OPEN')
        is_inplay = market.get('inPlay', False)
        
        if self.market_status == 'SUSPENDED':
            self.market_status_label.configure(text="SOSPESO", text_color=COLORS['loss'])
            self.dutch_modal_btn.configure(state=tk.DISABLED)
            self.place_btn.configure(state=tk.DISABLED)
        elif self.market_status == 'CLOSED':
            self.market_status_label.configure(text="CHIUSO", text_color=COLORS['text_secondary'])
            self.dutch_modal_btn.configure(state=tk.DISABLED)
            self.place_btn.configure(state=tk.DISABLED)
        else:
            if is_inplay:
                self.market_status_label.configure(text="LIVE - APERTO", text_color=COLORS['success'])
            else:
                self.market_status_label.configure(text="APERTO", text_color=COLORS['success'])
            self.dutch_modal_btn.configure(state=tk.NORMAL)
        
        runners_data = []
        for runner in market['runners']:
            back_price = f"{runner['backPrice']:.2f}" if runner.get('backPrice') else "-"
            lay_price = f"{runner['layPrice']:.2f}" if runner.get('layPrice') else "-"
            back_size = f"{runner['backSize']:.0f}" if runner.get('backSize') else "-"
            lay_size = f"{runner['laySize']:.0f}" if runner.get('laySize') else "-"
            
            sel_indicator = 'X' if str(runner['selectionId']) in self.selected_runners else ''
            
            runners_data.append({
                'id': runner['selectionId'],
                'values': (sel_indicator, runner['runnerName'], back_price, back_size, lay_price, lay_size),
                'tags': ('runner_row',)
            })

        self.tm_runners.update_flat(
            data=runners_data,
            id_getter=lambda r: str(r['id']),
            values_getter=lambda r: r['values'],
            tags_getter=lambda r: r['tags']
        )
        
        if self.market_status not in ('SUSPENDED', 'CLOSED'):
            self.stream_var.set(True)
            self._start_streaming()
        
        self._update_placed_bets()
        self._update_market_cashout_positions()
        
        if self.market_live_tracking_var.get() and not self.market_live_tracking_id:
            self._start_market_live_tracking()
    
    def _refresh_prices(self):
        """Manually refresh prices for current market."""
        if not self.current_market:
            return
        self._load_market(self.current_market['marketId'])
    
    def _toggle_streaming(self):
        """Toggle streaming on/off."""
        if self.stream_var.get():
            self._start_streaming()
        else:
            self._stop_streaming()
    
    def _start_streaming(self):
        """Start streaming prices for current market."""
        if not self.client or not self.current_market:
            self.stream_var.set(False)
            return
        
        try:
            self.client.start_streaming(
                [self.current_market['marketId']],
                self._on_price_update
            )
            self.streaming_active = True
            self.stream_label.configure(text="STREAMING ATTIVO")
        except Exception as e:
            self.stream_var.set(False)
            messagebox.showerror("Errore Streaming", str(e))
    
    def _stop_streaming(self):
        """Stop streaming."""
        if self.client:
            self.client.stop_streaming()
        self.streaming_active = False
        self.stream_var.set(False)
        self.stream_label.configure(text="")
    
    def _on_price_update(self, market_id, runners_data):
        """Handle streaming price update with throttling lock."""
        if not self.current_market or market_id != self.current_market['marketId']:
            return
        
        with self._buffer_lock:
            self._market_update_buffer[market_id] = runners_data
            if not getattr(self, '_pending_tree_update', False):
                self._pending_tree_update = True
                self.root.after(200, self._throttled_refresh)

    def _throttled_refresh(self):
        """Process buffered streaming updates at safe intervals."""
        with self._buffer_lock:
            snapshot = dict(self._market_update_buffer)
            self._market_update_buffer.clear()
            self._pending_tree_update = False
            
        if not self.current_market:
            return
            
        market_id = self.current_market['marketId']
        runners_data = snapshot.get(market_id)
        if not runners_data:
            return
            
        def update_ui():
            for runner_update in runners_data:
                selection_id = str(runner_update['selectionId'])
                try:
                    item = self.runners_tree.item(selection_id)
                    if not item:
                        continue
                        
                    current_values = list(item['values'])
                    back_prices = runner_update.get('backPrices', [])
                    lay_prices = runner_update.get('layPrices', [])
                    
                    if back_prices:
                        best_back = back_prices[0]
                        current_values[2] = f"{best_back[0]:.2f}"
                        current_values[3] = f"{best_back[1]:.0f}" if len(best_back) > 1 else "-"
                    
                    if lay_prices:
                        best_lay = lay_prices[0]
                        current_values[4] = f"{best_lay[0]:.2f}"
                        current_values[5] = f"{best_lay[1]:.0f}" if len(best_lay) > 1 else "-"
                    
                    self.runners_tree.item(selection_id, values=current_values)
                    
                    if selection_id in self.selected_runners:
                        if back_prices:
                            self.selected_runners[selection_id]['backPrice'] = back_prices[0][0]
                        if lay_prices:
                            self.selected_runners[selection_id]['layPrice'] = lay_prices[0][0]
                        bet_type = self.bet_type_var.get()
                        if bet_type == 'BACK' and back_prices:
                            self.selected_runners[selection_id]['price'] = back_prices[0][0]
                        elif bet_type == 'LAY' and lay_prices:
                            self.selected_runners[selection_id]['price'] = lay_prices[0][0]
                        self._recalculate()
                        
                except Exception:
                    pass
        
        self.uiq.post(update_ui)
    
    def _show_runner_context_menu(self, event):
        """Show context menu on right-click."""
        item = self.runners_tree.identify_row(event.y)
        if item:
            self.runners_tree.selection_set(item)
            self._context_menu_selection = item
            self.runner_context_menu.post(event.x_root, event.y_root)
    
    def _book_selected_runner(self):
        """Book the selected runner from context menu."""
        if not hasattr(self, '_context_menu_selection') or not self._context_menu_selection:
            return
        
        selection_id = self._context_menu_selection
        if not self.current_market:
            return
        
        for runner in self.current_market['runners']:
            if str(runner['selectionId']) == selection_id:
                current_price = runner.get('backPrice') or runner.get('layPrice') or 0
                if current_price > 0:
                    self._show_booking_dialog(
                        selection_id,
                        runner['runnerName'],
                        current_price,
                        self.current_market['marketId']
                    )
                break
    
    def _on_runner_clicked(self, event):
        """Handle runner row click - check which column was clicked for quick betting."""
        item = self.runners_tree.identify_row(event.y)
        if not item:
            return
        
        column = self.runners_tree.identify_column(event.x)
        selection_id = item
        
        if column == '#3':
            self._quick_bet(selection_id, 'BACK')
            return
        
        if column == '#5':
            self._quick_bet(selection_id, 'LAY')
            return
        
        if selection_id in self.selected_runners:
            del self.selected_runners[selection_id]
            values = list(self.runners_tree.item(item)['values'])
            values[0] = ''
            self.runners_tree.item(item, values=values)
        else:
            if self.current_market:
                for runner in self.current_market['runners']:
                    if str(runner['selectionId']) == selection_id:
                        runner_data = runner.copy()
                        
                        values = list(self.runners_tree.item(item)['values'])
                        try:
                            back_price = float(str(values[2]).replace(',', '.')) if values[2] and values[2] != '-' else 0
                            lay_price = float(str(values[4]).replace(',', '.')) if values[4] and values[4] != '-' else 0
                        except (ValueError, IndexError):
                            back_price = 0
                            lay_price = 0
                        
                        runner_data['backPrice'] = back_price
                        runner_data['layPrice'] = lay_price
                        bet_type = self.bet_type_var.get()
                        runner_data['price'] = back_price if bet_type == 'BACK' else lay_price
                        
                        self.selected_runners[selection_id] = runner_data
                        values[0] = 'X'
                        self.runners_tree.item(item, values=values)
                        break
        
        self._recalculate()
    
    def _quick_bet(self, selection_id, bet_type):
        """Place a quick single bet on a runner at current price."""
        if not self.client and not self.simulation_mode:
            messagebox.showwarning("Attenzione", "Devi prima connetterti")
            return
        
        if not self.current_market:
            return
        
        runner = None
        for r in self.current_market['runners']:
            if str(r['selectionId']) == selection_id:
                runner = r
                break
        
        if not runner:
            return
        
        values = list(self.runners_tree.item(selection_id)['values'])
        try:
            if bet_type == 'BACK':
                price = float(str(values[2]).replace(',', '.')) if values[2] and values[2] != '-' else 0
            else:
                price = float(str(values[4]).replace(',', '.')) if values[4] and values[4] != '-' else 0
        except (ValueError, IndexError):
            price = 0
        
        if price <= 0:
            messagebox.showwarning("Attenzione", "Quota non disponibile")
            return
        
        try:
            stake = float(self.stake_var.get().replace(',', '.'))
        except ValueError:
            stake = 1.0
        
        if stake < 1.0:
            stake = 1.0
        
        tipo_text = "Back (Punta)" if bet_type == 'BACK' else "Lay (Banca)"
        mode_text = "[SIMULAZIONE] " if self.simulation_mode else ""
        
        if not messagebox.askyesno("Conferma Scommessa Rapida",
            f"{mode_text}Vuoi piazzare questa scommessa?\n\n"
            f"Selezione: {runner['runnerName']}\n"
            f"Tipo: {tipo_text}\n"
            f"Quota: {price:.2f}\n"
            f"Stake: {stake:.2f} EUR"):
            return
        
        if self.simulation_mode:
            self._place_quick_simulation_bet(runner, bet_type, price, stake)
        else:
            self._place_quick_real_bet(runner, bet_type, price, stake)
    
    def _place_quick_simulation_bet(self, runner, bet_type, price, stake):
        """Place a quick simulated bet."""
        try:
            commission = 0.045
            if bet_type == 'BACK':
                gross_profit = stake * (price - 1)
                profit = gross_profit * (1 - commission)
                liability = stake
            else:
                gross_profit = stake
                profit = gross_profit * (1 - commission)
                liability = stake * (price - 1)
            
            settings = self.db.get_simulation_settings()
            current_balance = settings.get('virtual_balance', 10000.0)
            
            if liability > current_balance:
                messagebox.showerror("Errore Simulazione", 
                    f"Saldo virtuale insufficiente.\n"
                    f"Saldo: {format_currency(current_balance)}\n"
                    f"Richiesto: {format_currency(liability)}")
                return
            
            new_balance = current_balance - liability
            self.db.increment_simulation_bet_count(new_balance)
            
            self.db.save_simulation_bet(
                event_name=self.current_market.get('eventName', 'Quick Bet'),
                market_id=self.current_market['marketId'],
                market_name=self.current_market.get('marketName', ''),
                side=bet_type,
                selection_id=str(runner['selectionId']),
                selection_name=runner['runnerName'],
                price=price,
                stake=stake,
                status='MATCHED'
            )
            
            messagebox.showinfo("Simulazione", 
                f"Scommessa simulata piazzata!\n\n"
                f"{runner['runnerName']} @ {price:.2f}\n"
                f"Stake: {format_currency(stake)}\n"
                f"Nuovo Saldo: {format_currency(new_balance)}")
            
        except Exception as e:
            messagebox.showerror("Errore", str(e))
    
    def _place_quick_real_bet(self, runner, bet_type, price, stake):
        """Place a quick real bet via Betfair API."""
        def place_thread():
            try:
                result = self.client.place_bet(
                    market_id=self.current_market['marketId'],
                    selection_id=runner['selectionId'],
                    side=bet_type,
                    price=price,
                    size=stake,
                    persistence_type='LAPSE'
                )
                
                bet_result = result
                self.uiq.post(self._on_quick_bet_result, bet_result, runner, bet_type, price, stake)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", err_msg)
        
        self.executor.submit("quick_bet", place_thread)
    
    def _on_quick_bet_result(self, result, runner, bet_type, price, stake):
        """Handle quick bet result."""
        if result.get('status') == 'SUCCESS':
            matched = sum(r.get('sizeMatched', 0) for r in result.get('instructionReports', []))
            
            self.db.save_bet(
                event_name=self.current_market.get('eventName', ''),
                market_id=self.current_market['marketId'],
                market_name=self.current_market.get('marketName', ''),
                bet_type=bet_type,
                selections=runner['runnerName'],
                total_stake=stake,
                potential_profit=(stake * (price - 1)) * 0.955 if bet_type == 'BACK' else stake * 0.955,
                status='MATCHED' if matched > 0 else 'UNMATCHED'
            )
            
            messagebox.showinfo("Successo", 
                f"Scommessa piazzata!\n\n"
                f"{runner['runnerName']} @ {price:.2f}\n"
                f"Importo matchato: {format_currency(matched)}")
            
            self._update_balance()
        else:
            messagebox.showwarning("Attenzione", f"Stato: {result.get('status')}")
    
    def _set_bet_type(self, bet_type):
        """Set the bet type and update button colors."""
        self.bet_type_var.set(bet_type)
        
        if bet_type == 'BACK':
            self.back_btn.configure(fg_color=COLORS['back'])
            self.lay_btn.configure(fg_color=COLORS['button_secondary'])
        else:
            self.back_btn.configure(fg_color=COLORS['button_secondary'])
            self.lay_btn.configure(fg_color=COLORS['lay'])
        
        self._recalculate()
    
    def _clear_selections(self):
        """Clear all selections."""
        self.selected_runners = {}
        
        for item in self.runners_tree.get_children():
            values = list(self.runners_tree.item(item)['values'])
            values[0] = ''
            self.runners_tree.item(item, values=values)
        
        self.selections_text.configure(state=tk.NORMAL)
        self.selections_text.delete('1.0', tk.END)
        self.selections_text.configure(state=tk.DISABLED)
        
        self.profit_label.configure(text="Profitto: -")
        self.prob_label.configure(text="Probabilita Implicita: -")
        self.place_btn.configure(state=tk.DISABLED)
        self.calculated_results = None
    
    def _recalculate(self):
        """Recalculate dutching stakes."""
        if not self.selected_runners:
            self.selections_text.configure(state=tk.NORMAL)
            self.selections_text.delete('1.0', tk.END)
            self.selections_text.configure(state=tk.DISABLED)
            self.profit_label.configure(text="Profitto: -")
            self.prob_label.configure(text="Probabilita Implicita: -")
            self.place_btn.configure(state=tk.DISABLED)
            return
        
        self.selections_text.configure(state=tk.NORMAL)
        self.selections_text.delete('1.0', tk.END)
        
        try:
            total_stake = float(self.stake_var.get().replace(',', '.'))
        except ValueError:
            total_stake = 10.0
        
        bet_type = self.bet_type_var.get()
        
        for sel_id, sel in self.selected_runners.items():
            if bet_type == 'BACK':
                sel['price'] = sel.get('backPrice', 0)
            else:
                sel['price'] = sel.get('layPrice', 0)
        
        selections = list(self.selected_runners.values())
        
        try:
            results, profit, implied_prob = calculate_dutching_stakes(
                selections, total_stake, bet_type
            )
            
            text_lines = []
            for r in results:
                text_lines.append(f"{r['runnerName']}")
                text_lines.append(f"  Quota: {r['price']:.2f}")
                text_lines.append(f"  Stake: {format_currency(r['stake'])}")
                if bet_type == 'LAY':
                    text_lines.append(f"  Liability: {format_currency(r.get('liability', 0))}")
                    text_lines.append(f"  Se vince: {format_currency(r['profitIfWins'])}")
                else:
                    text_lines.append(f"  Profitto se vince: {format_currency(r['profitIfWins'])}")
                text_lines.append("")
            
            self.selections_text.insert('1.0', '\n'.join(text_lines))
            
            if bet_type == 'LAY' and results:
                best = results[0].get('bestCase', profit)
                worst = results[0].get('worstCase', 0)
                self.profit_label.configure(text=f"Profitto Max: {format_currency(best)} | Rischio: {format_currency(worst)}")
            else:
                self.profit_label.configure(text=f"Profitto Atteso: {format_currency(profit)}")
            self.prob_label.configure(text=f"Probabilita Implicita: {implied_prob:.1f}%")
            
            errors = validate_selections(results, bet_type)
            if not errors:
                self.place_btn.configure(state=tk.NORMAL)
            else:
                self.place_btn.configure(state=tk.DISABLED)
                self.selections_text.insert(tk.END, "\nErrori:\n" + "\n".join(errors))
            
            self.calculated_results = results
            
        except Exception as e:
            self.selections_text.insert('1.0', f"Errore calcolo: {e}")
            self.profit_label.configure(text="Profitto: -")
            self.place_btn.configure(state=tk.DISABLED)
        
        self.selections_text.configure(state=tk.DISABLED)
    
    def _open_dutching_window(self):
        """Open advanced Dutching Confirmation window."""
        if not self.current_market:
            messagebox.showwarning("Attenzione", "Seleziona prima un mercato.")
            return
        
        if not self.client:
            messagebox.showwarning("Attenzione", "Connettiti prima a Betfair.")
            return
        
        market_id = self.current_market['marketId']
        market_name = self.current_market.get('marketName', '')
        event_name = self.current_event.get('name', '') if self.current_event else ''
        start_time = self.current_event.get('openDate', '')[:16] if self.current_event else ''
        status = self.market_status
        
        runners = []
        for item in self.runners_tree.get_children():
            values = self.runners_tree.item(item, 'values')
            sel_id = self.runners_tree.item(item, 'tags')[0] if self.runners_tree.item(item, 'tags') else None
            
            if sel_id:
                try:
                    back_price = float(values[2]) if values[2] else 0
                except (ValueError, IndexError):
                    back_price = 0
                
                runners.append({
                    'selectionId': int(sel_id),
                    'runnerName': values[1] if len(values) > 1 else '',
                    'price': back_price
                })
        
        if not runners:
            messagebox.showwarning("Attenzione", "Nessun runner disponibile.")
            return
        
        market_data = {
            'marketId': market_id,
            'marketName': market_name,
            'eventName': event_name,
            'startTime': start_time,
            'status': status
        }
        
        def on_submit(orders):
            self._place_dutching_orders(orders)
        
        def on_refresh():
            self._refresh_market_prices()
        
        open_dutching_window(
            parent=self.root,
            market_data=market_data,
            runners=runners,
            on_submit=on_submit,
            on_refresh=on_refresh
        )
    
    def _place_dutching_orders(self, orders):
        """Place orders from Dutching Confirmation window."""
        if not orders:
            return
        
        if not self.current_market or not self.client:
            messagebox.showerror("Errore", "Connessione o mercato non disponibile.")
            return
        
        market_id = self.current_market['marketId']
        
        if self.simulation_mode:
            for order in orders:
                self.db.add_simulated_bet(
                    market_id=market_id,
                    selection_id=order['selectionId'],
                    runner_name=order['runnerName'],
                    side=order['side'],
                    price=order['price'],
                    stake=order['size']
                )
            messagebox.showinfo("Simulazione", f"Piazzati {len(orders)} ordini simulati.")
            return
        
        try:
            instructions = []
            for order in orders:
                instructions.append({
                    'selectionId': order['selectionId'],
                    'side': order['side'],
                    'orderType': 'LIMIT',
                    'limitOrder': {
                        'size': round(order['size'], 2),
                        'price': order['price'],
                        'persistenceType': 'LAPSE'
                    }
                })
            
            result = self.client.place_orders(market_id, instructions)
            
            if result and result.get('status') == 'SUCCESS':
                messagebox.showinfo("Successo", f"Piazzati {len(orders)} ordini Dutching.")
                self._refresh_data()
            else:
                error_msg = result.get('errorCode', 'Errore sconosciuto') if result else 'Nessuna risposta'
                messagebox.showerror("Errore", f"Errore piazzamento: {error_msg}")
                
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {str(e)}")
    
    def _place_bets(self):
        """Place the calculated bets (real or simulated)."""
        if hasattr(self, '_placing_in_progress') and self._placing_in_progress:
            return
        
        if not hasattr(self, 'calculated_results') or not self.calculated_results:
            return
        
        if not self.current_market:
            return
        
        if self.market_status == 'SUSPENDED':
            messagebox.showwarning("Mercato Sospeso", 
                "Il mercato e' attualmente sospeso.\nAttendi che riapra per piazzare scommesse.")
            return
        
        if self.market_status == 'CLOSED':
            messagebox.showwarning("Mercato Chiuso", 
                "Il mercato e' chiuso. Non e' possibile piazzare scommesse.")
            return
        
        total_stake = sum(r['stake'] for r in self.calculated_results)
        potential_profit = self.calculated_results[0].get('profitIfWins', 0)
        bet_type = self.bet_type_var.get()
        
        if self.simulation_mode:
            sim_settings = self.db.get_simulation_settings()
            virtual_balance = sim_settings.get('virtual_balance', 0) if sim_settings else 0
            
            if total_stake > virtual_balance:
                messagebox.showwarning("Saldo Insufficiente", 
                    f"Saldo virtuale insufficiente.\n\n"
                    f"Stake richiesto: {format_currency(total_stake)}\n"
                    f"Saldo disponibile: {format_currency(virtual_balance)}")
                return
            
            msg = f"[SIMULAZIONE] Confermi il piazzamento virtuale?\n\n"
            msg += f"Scommesse: {len(self.calculated_results)}\n"
            msg += f"Stake Totale: {format_currency(total_stake)}\n"
            msg += f"Profitto Potenziale: {format_currency(potential_profit)}\n\n"
            msg += f"Saldo Attuale: {format_currency(virtual_balance)}\n"
            msg += f"Saldo Dopo: {format_currency(virtual_balance - total_stake)}"
        else:
            msg = f"Confermi il piazzamento di {len(self.calculated_results)} scommesse?\n\n"
            msg += f"Stake Totale: {format_currency(total_stake)}"
        
        if not messagebox.askyesno("Conferma Scommesse", msg):
            return
        
        use_best_price = self.best_price_var.get()
        market_id = self.current_market['marketId']
        
        self.place_btn.configure(state=tk.DISABLED)
        self._placing_in_progress = True
        
        if self.simulation_mode:
            self._place_simulation_bets(total_stake, potential_profit, bet_type)
            self._placing_in_progress = False
            return
        
        def place():
            try:
                instructions = []
                
                if use_best_price:
                    book = self.client.get_market_book(market_id)
                    current_prices = {}
                    if book and book.get('runners'):
                        for runner in book['runners']:
                            sel_id = runner.get('selectionId')
                            ex = runner.get('ex', {})
                            if bet_type == 'BACK':
                                backs = ex.get('availableToBack', [])
                                if backs:
                                    current_prices[sel_id] = backs[0].get('price', 1.01)
                            else:  # LAY
                                lays = ex.get('availableToLay', [])
                                if lays:
                                    current_prices[sel_id] = lays[0].get('price', 1000)
                    
                    for r in self.calculated_results:
                        sel_id = r['selectionId']
                        price = current_prices.get(sel_id, r['price'])
                        instructions.append({
                            'selectionId': sel_id,
                            'side': bet_type,
                            'price': price,
                            'size': r['stake']
                        })
                else:
                    for r in self.calculated_results:
                        instructions.append({
                            'selectionId': r['selectionId'],
                            'side': bet_type,
                            'price': r['price'],
                            'size': r['stake']
                        })
                
                result = self.client.place_bets(market_id, instructions)
                reports = result.get('instructionReports', [])
                
                all_matched = all(r.get('status') == 'SUCCESS' and r.get('sizeMatched', 0) > 0 for r in reports)
                any_matched = any(r.get('sizeMatched', 0) > 0 for r in reports)
                
                if result['status'] == 'SUCCESS':
                    if all_matched:
                        bet_status = 'MATCHED'
                    elif any_matched:
                        bet_status = 'PARTIALLY_MATCHED'
                    else:
                        bet_status = 'PENDING'
                elif result['status'] == 'FAILURE':
                    bet_status = 'FAILED'
                else:
                    bet_status = result['status']
                
                selections_with_names = []
                for i, r in enumerate(self.calculated_results):
                    report = reports[i] if i < len(reports) else {}
                    selections_with_names.append({
                        'runnerName': r.get('runnerName', 'Unknown'),
                        'selectionId': r['selectionId'],
                        'price': r['price'],
                        'stake': r['stake'],
                        'sizeMatched': report.get('sizeMatched', 0),
                        'betId': report.get('betId'),
                        'instructionStatus': report.get('status', 'UNKNOWN')
                    })
                
                self.db.save_bet(
                    self.current_event['name'],
                    self.current_market['marketId'],
                    self.current_market['marketName'],
                    bet_type,
                    selections_with_names,
                    total_stake,
                    self.calculated_results[0]['profitIfWins'],
                    bet_status
                )
                
                self.uiq.post(self._on_bets_placed, result)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(self._on_bets_error, err_msg)
        
        self.executor.submit("place_bets_task", place)
    
    def _place_simulation_bets(self, total_stake, potential_profit, bet_type):
        """Place simulated bets without calling Betfair API."""
        try:
            sim_settings = self.db.get_simulation_settings()
            virtual_balance = sim_settings.get('virtual_balance', 0)
            
            new_balance = virtual_balance - total_stake
            self.db.increment_simulation_bet_count(new_balance)
            
            selections_info = [
                {'name': r.get('runnerName', 'Unknown'), 
                 'price': r['price'], 
                 'stake': r['stake']}
                for r in self.calculated_results
            ]
            
            self.db.save_simulation_bet(
                event_name=self.current_event['name'],
                market_id=self.current_market['marketId'],
                market_name=self.current_market['marketName'],
                side=bet_type,
                selections=selections_info,
                total_stake=total_stake,
                potential_profit=potential_profit
            )
            
            self._update_simulation_balance_display()
            self.place_btn.configure(state=tk.NORMAL)
            
            messagebox.showinfo("Simulazione", 
                f"Scommessa virtuale piazzata!\n\n"
                f"Stake: {format_currency(total_stake)}\n"
                f"Profitto Potenziale: {format_currency(potential_profit)}\n"
                f"Nuovo Saldo Virtuale: {format_currency(new_balance)}")
            
            self._clear_selections()
            
        except Exception as e:
            self.place_btn.configure(state=tk.NORMAL)
            messagebox.showerror("Errore Simulazione", f"Errore: {e}")
    
    def _on_bets_placed(self, result):
        """Handle successful bet placement."""
        self._placing_in_progress = False
        self.place_btn.configure(state=tk.NORMAL)
        
        if result['status'] == 'SUCCESS':
            matched = sum(r.get('sizeMatched', 0) for r in result.get('instructionReports', []))
            messagebox.showinfo("Successo", f"Scommesse piazzate!\nImporto matchato: {format_currency(matched)}")
            self._update_balance()
            self._clear_selections()
        else:
            messagebox.showwarning("Attenzione", f"Stato: {result['status']}")
    
    def _on_bets_error(self, error):
        """Handle bet placement error."""
        self._placing_in_progress = False
        self.place_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Errore", f"Errore piazzamento: {error}")
    
    def _show_about(self):
        """Show about dialog."""
        from database import get_db_path
        db_path = get_db_path()
        market_list = "\n".join([f"- {v}" for k, v in list(MARKET_TYPES.items())[:8]])
        messagebox.showinfo(
            "Informazioni",
            f"{APP_NAME}\n"
            f"Versione {APP_VERSION}\n\n"
            "Applicazione per dutching su Betfair Exchange Italia.\n\n"
            "Mercati supportati:\n"
            f"{market_list}\n"
            "...e altri\n\n"
            "Funzionalita:\n"
            "- Streaming quote in tempo reale\n"
            "- Calcolo automatico stake dutching\n"
            "- Dashboard con saldo e scommesse\n"
            "- Prenotazione quote\n"
            "- Cashout automatico\n\n"
            f"Database:\n{db_path}\n\n"
            "Requisiti:\n"
            "- Account Betfair Italia\n"
            "- Certificato SSL per API\n"
            "- App Key Betfair"
        )
    
    def _check_for_updates_on_startup(self):
        """Check for updates when app starts."""
        settings = self.db.get_settings() or {}
        
        update_url = settings.get('update_url') or DEFAULT_UPDATE_URL
        if not update_url:
            return
        
        skipped_version = settings.get('skipped_version')
        
        def on_update_result(result):
            if result.get('update_available'):
                latest = result.get('latest_version', '')
                if skipped_version and latest == skipped_version:
                    return
                self.root.after(100, lambda: self.uiq.post(self._show_update_notification, result))
        
        check_for_updates(APP_VERSION, callback=on_update_result, update_url=update_url)
    
    def _show_update_notification(self, update_info):
        """Show update notification dialog."""
        choice = show_update_dialog(self.root, update_info)
        
        if choice == 'skip':
            self.db.save_skipped_version(update_info.get('latest_version'))
    
    def _check_for_updates_manual(self):
        """Manually check for updates."""
        settings = self.db.get_settings() or {}
        update_url = settings.get('update_url') or DEFAULT_UPDATE_URL
        
        if not update_url:
            messagebox.showinfo("Aggiornamenti", 
                "Nessun URL di aggiornamento configurato.\n\n"
                "Vai su File > Configura Aggiornamenti per impostarlo.")
            return
        
        def on_result(result):
            if result.get('update_available'):
                self.uiq.post(self._show_update_notification, result)
            elif result.get('error'):
                self.uiq.post(messagebox.showerror, "Errore", f"Impossibile verificare aggiornamenti:\n{result.get('error')}")
            else:
                self.uiq.post(messagebox.showinfo, "Aggiornamenti", f"Hai gia' l'ultima versione ({APP_VERSION})!")
        
        check_for_updates(APP_VERSION, callback=on_result, update_url=update_url)
    
    def _show_update_settings_dialog(self):
        """Show dialog to configure auto-updates."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Aggiornamenti")
        dialog.geometry("500x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Configura Aggiornamenti Automatici", 
                  style='Title.TLabel').pack(pady=(0, 15))
        
        settings = self.db.get_settings() or {}
        
        ttk.Label(frame, text="URL GitHub Releases API:").pack(anchor=tk.W)
        ttk.Label(frame, text=f"(Default: {DEFAULT_UPDATE_URL})", 
                  foreground='gray', font=('Segoe UI', 8)).pack(anchor=tk.W)
        
        url_var = tk.StringVar(value=settings.get('update_url', '') or DEFAULT_UPDATE_URL)
        url_entry = ttk.Entry(frame, textvariable=url_var, width=60)
        url_entry.pack(fill=tk.X, pady=(5, 15))
        
        ttk.Label(frame, text="L'app controllera' automaticamente gli aggiornamenti all'avvio.", 
                  foreground='gray').pack(anchor=tk.W)
        
        def save():
            self.db.save_update_url(url_var.get().strip())
            self.db.save_skipped_version(None)
            dialog.destroy()
            messagebox.showinfo("Salvato", "Impostazioni aggiornamento salvate!")
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=15)
        ttk.Button(btn_frame, text="Salva", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annulla", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Verifica Ora", 
                   command=lambda: [dialog.destroy(), self._check_for_updates_manual()]).pack(side=tk.RIGHT, padx=5)
    
    def _toggle_live_mode(self):
        """Toggle live-only mode."""
        if not self.client:
            messagebox.showwarning("Attenzione", "Devi prima connetterti")
            return
        
        self.live_mode = not self.live_mode
        
        if self.live_mode:
            self.live_btn.configure(fg_color=COLORS['success'], text="LIVE ON")
            self._load_live_events()
            self._start_live_refresh()
        else:
            self.live_btn.configure(fg_color=COLORS['loss'], text="LIVE")
            self._stop_live_refresh()
            self._load_events()
    
    def _load_live_events(self):
        """Load only live/in-play events."""
        if not self.client:
            return
        
        def fetch():
            try:
                events = self.client.get_live_events_only()
                self.uiq.post(self._display_events, events)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", err_msg)
        
        self.executor.submit("fetch_live_events", fetch)
    
    def _start_live_refresh(self):
        """Start auto-refresh for live odds."""
        self._stop_live_refresh()
        self._do_live_refresh()
    
    def _do_live_refresh(self):
        """Single live refresh cycle."""
        if not self.live_mode:
            return
        if self.current_market:
            self._refresh_prices()
        self.live_refresh_id = self.root.after(LIVE_REFRESH_INTERVAL, self._do_live_refresh)
    
    def _stop_live_refresh(self):
        """Stop auto-refresh for live odds."""
        if self.live_refresh_id:
            self.root.after_cancel(self.live_refresh_id)
            self.live_refresh_id = None
    
    def _create_dashboard_tab(self):
        """Create dashboard tab content."""
        main_frame = ctk.CTkFrame(self.dashboard_tab, fg_color='transparent')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Dashboard - Account Betfair Italy", 
                     font=FONTS['title'], text_color=COLORS['text_primary']).pack(anchor=tk.W, pady=(0, 20))
        
        self.dashboard_stats_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        self.dashboard_stats_frame.pack(fill=tk.X, pady=10)
        
        self.dashboard_not_connected = ctk.CTkLabel(main_frame, text="Connettiti a Betfair per vedere i dati", 
                                                    font=('Segoe UI', 11), text_color=COLORS['text_secondary'])
        self.dashboard_not_connected.pack(pady=20)
        
        ctk.CTkButton(main_frame, text="Aggiorna Dashboard", command=self._refresh_dashboard_tab,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6).pack(anchor=tk.E, pady=10)
        
        self.dashboard_notebook = ctk.CTkTabview(main_frame, fg_color=COLORS['bg_panel'],
                                                 segmented_button_fg_color=COLORS['bg_card'],
                                                 segmented_button_selected_color=COLORS['back'],
                                                 segmented_button_unselected_color=COLORS['bg_card'])
        self.dashboard_notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.dashboard_notebook.add("Scommesse Recenti")
        self.dashboard_notebook.add("Ordini Correnti")
        self.dashboard_notebook.add("Prenotazioni")
        self.dashboard_notebook.add("Cashout")
        
        self.dashboard_recent_frame = self.dashboard_notebook.tab("Scommesse Recenti")
        self.dashboard_orders_frame = self.dashboard_notebook.tab("Ordini Correnti")
        self.dashboard_bookings_frame = self.dashboard_notebook.tab("Prenotazioni")
        self.dashboard_cashout_frame = self.dashboard_notebook.tab("Cashout")
    
    def _refresh_dashboard_tab(self):
        """Refresh dashboard tab data."""
        if not self.client:
            self.dashboard_not_connected.configure(text="Connettiti a Betfair per vedere i dati")
            return
        
        self.dashboard_not_connected.configure(text="")
        
        def create_stat_card(parent, title, value, subtitle, col):
            card = ctk.CTkFrame(parent, fg_color=COLORS['bg_card'], corner_radius=8)
            card.grid(row=0, column=col, padx=5, sticky='nsew')
            ctk.CTkLabel(card, text=title, font=('Segoe UI', 9), 
                        text_color=COLORS['text_secondary']).pack(pady=(10, 2))
            ctk.CTkLabel(card, text=value, font=FONTS['title'], 
                        text_color=COLORS['text_primary']).pack()
            ctk.CTkLabel(card, text=subtitle, font=('Segoe UI', 8), 
                        text_color=COLORS['text_tertiary']).pack(pady=(2, 10))
            return card
        
        def fetch_data():
            try:
                funds = self.client.get_account_funds()
                self.account_data = funds
                daily_pl = self.db.get_today_profit_loss()
                try:
                    orders = self.client.get_current_orders()
                    active_count = len([o for o in orders.get('matched', []) if o.get('sizeMatched', 0) > 0])
                except:
                    active_count = self.db.get_active_bets_count()
                
                try:
                    settled_bets = self.client.get_settled_bets(days=7)
                except:
                    settled_bets = []
                
                self.uiq.post(update_ui, funds, daily_pl, active_count, orders, settled_bets)
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", err_msg)
        
        def update_ui(funds, daily_pl, active_count, orders, settled_bets=None):
            for widget in self.dashboard_stats_frame.winfo_children():
                widget.destroy()
            
            create_stat_card(self.dashboard_stats_frame, "Saldo Disponibile", 
                            f"{funds.get('available', 0):.2f} EUR", 
                            "Fondi disponibili", 0)
            create_stat_card(self.dashboard_stats_frame, "Esposizione", 
                            f"{abs(funds.get('exposure', 0)):.2f} EUR", 
                            "Responsabilita corrente", 1)
            pl_text = f"+{daily_pl:.2f}" if daily_pl >= 0 else f"{daily_pl:.2f}"
            create_stat_card(self.dashboard_stats_frame, "P/L Oggi", 
                            f"{pl_text} EUR", 
                            "Profitto/Perdita giornaliero", 2)
            create_stat_card(self.dashboard_stats_frame, "Scommesse Attive", 
                            str(active_count), 
                            "In attesa di risultato", 3)
            
            for i in range(4):
                self.dashboard_stats_frame.columnconfigure(i, weight=1)
            
            for widget in self.dashboard_recent_frame.winfo_children():
                widget.destroy()
            self._create_settled_bets_list(self.dashboard_recent_frame, settled_bets or [])
            
            for widget in self.dashboard_orders_frame.winfo_children():
                widget.destroy()
            self._create_current_orders_view(self.dashboard_orders_frame)
            
            for widget in self.dashboard_bookings_frame.winfo_children():
                widget.destroy()
            self._create_bookings_view(self.dashboard_bookings_frame)
            
            for widget in self.dashboard_cashout_frame.winfo_children():
                widget.destroy()
            self._create_cashout_view(self.dashboard_cashout_frame, None)
        
        self.executor.submit("refresh_dashboard", fetch_data)
    
    def _create_simulation_bets_list(self, parent):
        """Create list of simulation bets."""
        sim_bets = self.db.get_simulation_bets(limit=50)
        sim_settings = self.db.get_simulation_settings()
        
        if sim_settings:
            balance = sim_settings.get('virtual_balance', 1000)
            starting = sim_settings.get('starting_balance', 1000)
            pl = balance - starting
            pl_text = f"+{pl:.2f}" if pl >= 0 else f"{pl:.2f}"
            info_frame = ttk.Frame(parent)
            info_frame.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(info_frame, text=f"Saldo Simulato: {balance:.2f} EUR", 
                     font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
            ttk.Label(info_frame, text=f"  |  P/L: {pl_text} EUR", 
                     foreground='#28a745' if pl >= 0 else '#dc3545').pack(side=tk.LEFT)
        
        columns = ('data', 'evento', 'mercato', 'tipo', 'stake', 'profitto')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=12)
        tree.heading('data', text='Data')
        tree.heading('evento', text='Evento')
        tree.heading('mercato', text='Mercato')
        tree.heading('tipo', text='Tipo')
        tree.heading('stake', text='Stake')
        tree.heading('profitto', text='Profitto')
        tree.column('data', width=100)
        tree.column('evento', width=150)
        tree.column('mercato', width=120)
        tree.column('tipo', width=50)
        tree.column('stake', width=70)
        tree.column('profitto', width=80)
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if not sim_bets:
            ttk.Label(parent, text="Nessuna scommessa simulata", font=('Segoe UI', 10)).pack(pady=20)
        
        for bet in sim_bets:
            placed_at = bet.get('placed_at', '')[:16] if bet.get('placed_at') else ''
            profit = bet.get('potential_profit', 0)
            profit_display = f"+{profit:.2f}" if profit and profit > 0 else f"{profit:.2f}" if profit else "-"
            
            tree.insert('', tk.END, values=(
                placed_at,
                bet.get('event_name', '')[:25],
                bet.get('market_name', '')[:20],
                bet.get('side', ''),
                f"{bet.get('total_stake', 0):.2f}",
                profit_display
            ))
    
    def _create_telegram_tab(self):
        """Create Telegram tab content."""
        main_frame = ctk.CTkFrame(self.telegram_tab, fg_color='transparent')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_container = ctk.CTkFrame(main_frame, fg_color='transparent', width=450)
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        left_container.pack_propagate(False)
        
        left_canvas = tk.Canvas(left_container, highlightthickness=0, bg=COLORS['bg_dark'])
        left_scrollbar = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=left_canvas.yview)
        left_frame = ctk.CTkFrame(left_canvas, fg_color='transparent')
        
        left_frame.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=left_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        right_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        config_frame = ctk.CTkFrame(left_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        config_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        ctk.CTkLabel(config_frame, text="Configurazione Telegram", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        ctk.CTkLabel(config_frame, text="Ottieni API ID e Hash su my.telegram.org", 
                     font=('Segoe UI', 8), text_color=COLORS['text_tertiary']).pack(anchor=tk.W, padx=10)
        
        settings = self.db.get_telegram_settings() or {}
        
        ctk.CTkLabel(config_frame, text="API ID:", text_color=COLORS['text_secondary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.tg_api_id_var = tk.StringVar(value=settings.get('api_id', ''))
        ctk.CTkEntry(config_frame, textvariable=self.tg_api_id_var, width=200,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(anchor=tk.W, padx=10)
        
        ctk.CTkLabel(config_frame, text="API Hash:", text_color=COLORS['text_secondary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.tg_api_hash_var = tk.StringVar(value=settings.get('api_hash', ''))
        ctk.CTkEntry(config_frame, textvariable=self.tg_api_hash_var, width=200,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(anchor=tk.W, padx=10)
        
        ctk.CTkLabel(config_frame, text="Numero di Telefono (+39...):", text_color=COLORS['text_secondary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.tg_phone_var = tk.StringVar(value=settings.get('phone_number', ''))
        ctk.CTkEntry(config_frame, textvariable=self.tg_phone_var, width=150,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(anchor=tk.W, padx=10)
        
        ctk.CTkLabel(config_frame, text="Stake Automatico (EUR):", text_color=COLORS['text_secondary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.tg_auto_stake_var = tk.StringVar(value=str(settings.get('auto_stake', '1.0')))
        ctk.CTkEntry(config_frame, textvariable=self.tg_auto_stake_var, width=80,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(anchor=tk.W, padx=10)
        
        self.tg_auto_bet_var = tk.BooleanVar(value=bool(settings.get('auto_bet', 0)))
        ctk.CTkCheckBox(config_frame, text="Piazza automaticamente", variable=self.tg_auto_bet_var,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(5, 0))
        
        self.tg_confirm_var = tk.BooleanVar(value=bool(settings.get('require_confirmation', 1)))
        ctk.CTkCheckBox(config_frame, text="Richiedi conferma (solo se auto OFF)", variable=self.tg_confirm_var,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10)
        
        auth_frame = ctk.CTkFrame(config_frame, fg_color='transparent')
        auth_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        ctk.CTkLabel(auth_frame, text="Codice:", text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        self.tg_code_var = tk.StringVar()
        ctk.CTkEntry(auth_frame, textvariable=self.tg_code_var, width=60,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(side=tk.LEFT, padx=2)
        ctk.CTkLabel(auth_frame, text="2FA:", text_color=COLORS['text_secondary']).pack(side=tk.LEFT, padx=(10, 0))
        self.tg_2fa_var = tk.StringVar()
        ctk.CTkEntry(auth_frame, textvariable=self.tg_2fa_var, width=80, show='*',
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(auth_frame, text="Invia Codice", command=self._send_telegram_code,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=90).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(auth_frame, text="Verifica", command=self._verify_telegram_code,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=70).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(auth_frame, text="Reset Sessione", command=self._reset_telegram_session,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        
        self.tg_status_label = ctk.CTkLabel(config_frame, text=f"Stato: {self.telegram_status}",
                                            text_color=COLORS['text_secondary'])
        self.tg_status_label.pack(anchor=tk.W, padx=10, pady=5)
        
        btn_frame = ctk.CTkFrame(config_frame, fg_color='transparent')
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ctk.CTkButton(btn_frame, text="Salva", command=self._save_telegram_tab_settings,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=80).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(btn_frame, text="Avvia Listener", command=self._start_telegram_listener,
                      fg_color=COLORS['button_success'], hover_color='#4caf50',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(btn_frame, text="Ferma", command=self._stop_telegram_listener,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=70).pack(side=tk.LEFT, padx=2)
        
        chats_frame = ctk.CTkFrame(left_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        chats_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        ctk.CTkLabel(chats_frame, text="Chat Monitorate", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        chat_btn_frame = ctk.CTkFrame(chats_frame, fg_color='transparent')
        chat_btn_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        ctk.CTkButton(chat_btn_frame, text="Rimuovi", command=self._remove_telegram_chat,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=80).pack(side=tk.LEFT, padx=2)
        
        columns = ('name', 'enabled')
        self.tg_chats_tree = ttk.Treeview(chats_frame, columns=columns, show='headings', height=4)
        self.tg_chats_tree.heading('name', text='Nome Chat')
        self.tg_chats_tree.heading('enabled', text='Attivo')
        self.tg_chats_tree.column('name', width=200)
        self.tg_chats_tree.column('enabled', width=50)
        self.tg_chats_tree.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self._refresh_telegram_chats_tree()
        
        available_frame = ctk.CTkFrame(left_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        available_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        ctk.CTkLabel(available_frame, text="Chat Disponibili da Telegram", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        avail_btn_frame = ctk.CTkFrame(available_frame, fg_color='transparent')
        avail_btn_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        ctk.CTkButton(avail_btn_frame, text="Carica/Aggiorna Chat", command=self._load_available_chats,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=140).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(avail_btn_frame, text="Aggiungi Selezionate", command=self._add_selected_available_chats,
                      fg_color=COLORS['button_success'], hover_color='#4caf50',
                      corner_radius=6, width=140).pack(side=tk.LEFT, padx=2)
        
        self.tg_available_status = ctk.CTkLabel(avail_btn_frame, text="", text_color=COLORS['text_secondary'])
        self.tg_available_status.pack(side=tk.RIGHT, padx=5)
        
        avail_columns = ('select', 'type', 'name')
        avail_tree_container = ctk.CTkFrame(available_frame, fg_color='transparent')
        avail_tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.tg_available_tree = ttk.Treeview(avail_tree_container, columns=avail_columns, show='headings', height=8, selectmode='extended')
        self.tg_available_tree.heading('select', text='')
        self.tg_available_tree.heading('type', text='Tipo')
        self.tg_available_tree.heading('name', text='Nome')
        self.tg_available_tree.column('select', width=30)
        self.tg_available_tree.column('type', width=60)
        self.tg_available_tree.column('name', width=200)
        
        avail_scroll = ttk.Scrollbar(avail_tree_container, orient=tk.VERTICAL, command=self.tg_available_tree.yview)
        self.tg_available_tree.configure(yscrollcommand=avail_scroll.set)
        self.tg_available_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        avail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.available_chats_data = []
        
        rules_frame = ctk.CTkFrame(left_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        rules_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        ctk.CTkLabel(rules_frame, text="Regole di Parsing", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        ctk.CTkLabel(rules_frame, text="Definisci pattern regex per riconoscere i segnali", 
                     font=('Segoe UI', 8), text_color=COLORS['text_tertiary']).pack(anchor=tk.W, padx=10)
        
        rules_btn_frame = ctk.CTkFrame(rules_frame, fg_color='transparent')
        rules_btn_frame.pack(fill=tk.X, padx=10, pady=(5, 5))
        ctk.CTkButton(rules_btn_frame, text="Aggiungi", command=self._add_signal_pattern,
                      fg_color=COLORS['button_success'], hover_color='#4caf50',
                      corner_radius=6, width=80).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(rules_btn_frame, text="Modifica", command=self._edit_signal_pattern,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=80).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(rules_btn_frame, text="Elimina", command=self._delete_signal_pattern,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=80).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(rules_btn_frame, text="Attiva/Disattiva", command=self._toggle_signal_pattern,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=110).pack(side=tk.LEFT, padx=2)
        
        rules_columns = ('enabled', 'name', 'market', 'pattern')
        rules_tree_container = ctk.CTkFrame(rules_frame, fg_color='transparent')
        rules_tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.rules_tree = ttk.Treeview(rules_tree_container, columns=rules_columns, show='headings', height=6)
        self.rules_tree.heading('enabled', text='ON')
        self.rules_tree.heading('name', text='Nome')
        self.rules_tree.heading('market', text='Mercato')
        self.rules_tree.heading('pattern', text='Pattern')
        self.rules_tree.column('enabled', width=30)
        self.rules_tree.column('name', width=120)
        self.rules_tree.column('market', width=100)
        self.rules_tree.column('pattern', width=150)
        
        rules_scroll = ttk.Scrollbar(rules_tree_container, orient=tk.VERTICAL, command=self.rules_tree.yview)
        self.rules_tree.configure(yscrollcommand=rules_scroll.set)
        self.rules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rules_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._refresh_rules_tree()
        
        signals_frame = ctk.CTkFrame(right_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        signals_frame.pack(fill=tk.BOTH, expand=True)
        
        ctk.CTkLabel(signals_frame, text="Segnali Ricevuti", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        signals_tree_container = ctk.CTkFrame(signals_frame, fg_color='transparent')
        signals_tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        columns = ('data', 'selezione', 'tipo', 'quota', 'stake', 'stato')
        self.tg_signals_tree = ttk.Treeview(signals_tree_container, columns=columns, show='headings', height=15)
        self.tg_signals_tree.heading('data', text='Data')
        self.tg_signals_tree.heading('selezione', text='Selezione')
        self.tg_signals_tree.heading('tipo', text='Tipo')
        self.tg_signals_tree.heading('quota', text='Quota')
        self.tg_signals_tree.heading('stake', text='Stake')
        self.tg_signals_tree.heading('stato', text='Stato')
        self.tg_signals_tree.column('data', width=100)
        self.tg_signals_tree.column('selezione', width=150)
        self.tg_signals_tree.column('tipo', width=50)
        self.tg_signals_tree.column('quota', width=60)
        self.tg_signals_tree.column('stake', width=60)
        self.tg_signals_tree.column('stato', width=80)
        
        self.tg_signals_tree.tag_configure('success', foreground=COLORS['success'])
        self.tg_signals_tree.tag_configure('failed', foreground=COLORS['loss'])
        
        scrollbar = ttk.Scrollbar(signals_tree_container, orient=tk.VERTICAL, command=self.tg_signals_tree.yview)
        self.tg_signals_tree.configure(yscrollcommand=scrollbar.set)
        self.tg_signals_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        ctk.CTkButton(signals_frame, text="Aggiorna Segnali", command=self._refresh_telegram_signals_tree,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6).pack(pady=10)
        
        self._refresh_telegram_signals_tree()
    
    def _save_telegram_tab_settings(self):
        """Save Telegram settings from tab."""
        try:
            stake = float(self.tg_auto_stake_var.get().replace(',', '.'))
        except:
            stake = 1.0
        
        settings = self.db.get_telegram_settings() or {}
        self.db.save_telegram_settings(
            api_id=self.tg_api_id_var.get(),
            api_hash=self.tg_api_hash_var.get(),
            session_string=settings.get('session_string'),
            phone_number=self.tg_phone_var.get(),
            enabled=True,
            auto_bet=self.tg_auto_bet_var.get(),
            require_confirmation=self.tg_confirm_var.get(),
            auto_stake=stake
        )
        messagebox.showinfo("Salvato", "Impostazioni Telegram salvate")
    
    def _load_available_chats(self):
        """Load available chats from Telegram account into the tree."""
        settings = self.db.get_telegram_settings()
        if not settings or not settings.get('api_id') or not settings.get('api_hash'):
            messagebox.showwarning("Attenzione", "Configura prima le credenziali Telegram")
            return
        
        self.tg_available_status.configure(text="Caricamento...")
        self.tg_available_tree.delete(*self.tg_available_tree.get_children())
        self.available_chats_data = []
        
        def fetch_dialogs():
            try:
                import asyncio
                import os
                from telethon import TelegramClient
                from telethon.tl.types import Channel, Chat, User
                
                async def do_fetch():
                    api_id = int(settings['api_id'])
                    api_hash = settings['api_hash'].strip()
                    session_path = os.path.join(os.environ.get('APPDATA', '.'), 'Pickfair', 'telegram_session')
                    
                    client = TelegramClient(session_path, api_id, api_hash)
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        await client.disconnect()
                        return None
                    
                    dialogs = await client.get_dialogs()
                    chat_list = []
                    
                    for d in dialogs:
                        entity = d.entity
                        chat_type = 'Altro'
                        
                        if isinstance(entity, Channel):
                            chat_type = 'Canale' if entity.broadcast else 'Gruppo'
                        elif isinstance(entity, Chat):
                            chat_type = 'Gruppo'
                        elif isinstance(entity, User):
                            chat_type = 'Bot' if entity.bot else 'Utente'
                        
                        chat_list.append({
                            'id': d.id,
                            'name': d.name or str(d.id),
                            'type': chat_type
                        })
                    
                    await client.disconnect()
                    return chat_list
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(do_fetch())
                loop.close()
                
                if result is None:
                    self.uiq.post(self.tg_available_status.configure, text="Non autenticato")
                    self.uiq.post(messagebox.showwarning, "Attenzione", 
                        "Non autenticato. Clicca 'Invia Codice' e poi 'Verifica'.")
                else:
                    self.uiq.post(self._populate_available_chats, result)
                
            except Exception as e:
                err = str(e)
                self.uiq.post(self.tg_available_status.configure, text=f"Errore: {err[:30]}")
        
        self.executor.submit("fetch_telegram_dialogs", fetch_dialogs)
    
    def _populate_available_chats(self, chat_list):
        """Populate the available chats tree."""
        self.tg_available_tree.delete(*self.tg_available_tree.get_children())
        self.available_chats_data = chat_list
        
        monitored_ids = set()
        for chat in self.db.get_telegram_chats():
            monitored_ids.add(int(chat['chat_id']))
        
        for chat in chat_list:
            if chat['id'] in monitored_ids:
                continue
            self.tg_available_tree.insert('', tk.END, iid=str(chat['id']), values=(
                '',
                chat['type'],
                chat['name']
            ))
        
        count = len(self.tg_available_tree.get_children())
        self.tg_available_status.configure(text=f"{count} chat disponibili")
    
    def _add_selected_available_chats(self):
        """Add selected chats from available list to monitored."""
        selected = self.tg_available_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona almeno una chat dalla lista")
            return
        
        count = 0
        for item_id in selected:
            item = self.tg_available_tree.item(item_id)
            values = item['values']
            chat_id = int(item_id)
            chat_name = values[2] if len(values) > 2 else str(chat_id)
            
            self.db.add_telegram_chat(chat_id, chat_name)
            self.tg_available_tree.delete(item_id)
            count += 1
        
        self._refresh_telegram_chats_tree()
        remaining = len(self.tg_available_tree.get_children())
        self.tg_available_status.configure(text=f"{remaining} chat disponibili")
        messagebox.showinfo("Aggiunto", f"Aggiunte {count} chat alla lista monitorata")
    
    def _add_telegram_chat(self):
        """Add a new telegram chat to monitor."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Chat")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Chat ID:").pack(anchor=tk.W, padx=20, pady=(20, 5))
        chat_id_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=chat_id_var, width=40).pack(padx=20)
        
        ttk.Label(dialog, text="Nome Chat (opzionale):").pack(anchor=tk.W, padx=20, pady=(10, 5))
        chat_name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=chat_name_var, width=40).pack(padx=20)
        
        def save():
            chat_id = chat_id_var.get().strip()
            if not chat_id:
                messagebox.showwarning("Errore", "Inserisci un Chat ID")
                return
            try:
                chat_id_int = int(chat_id)
                chat_name = chat_name_var.get().strip() or f"Chat {chat_id}"
                self.db.add_telegram_chat(chat_id_int, chat_name)
                self._refresh_telegram_chats_tree()
                dialog.destroy()
                messagebox.showinfo("Successo", f"Chat '{chat_name}' aggiunta")
            except ValueError:
                messagebox.showwarning("Errore", "Chat ID deve essere un numero")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Salva", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annulla", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _remove_telegram_chat(self):
        """Remove selected telegram chat."""
        selected = self.tg_chats_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una chat da rimuovere")
            return
        
        item = self.tg_chats_tree.item(selected[0])
        chat_name = item['values'][0]
        
        if messagebox.askyesno("Conferma", f"Rimuovere la chat '{chat_name}'?"):
            chats = self.db.get_telegram_chats()
            for chat in chats:
                if chat.get('chat_name') == chat_name or str(chat['chat_id']) == chat_name:
                    self.db.remove_telegram_chat(chat['chat_id'])
                    break
            self._refresh_telegram_chats_tree()
    
    def _refresh_telegram_chats_tree(self):
        """Refresh chats tree in Telegram tab."""
        self.tg_chats_tree.delete(*self.tg_chats_tree.get_children())
        chats = self.db.get_telegram_chats()
        for chat in chats:
            self.tg_chats_tree.insert('', tk.END, values=(
                chat.get('chat_name', str(chat['chat_id'])),
                'Si' if chat.get('enabled') else 'No'
            ))
    
    def _refresh_telegram_signals_tree(self):
        """Refresh signals tree in Telegram tab."""
        self.tg_signals_tree.delete(*self.tg_signals_tree.get_children())
        signals = self.db.get_recent_signals(limit=50)
        for sig in signals:
            timestamp = sig.get('received_at', '')[:16]
            selection = sig.get('parsed_selection', '')[:25] if sig.get('parsed_selection') else 'N/A'
            side = sig.get('parsed_side', '')
            status = sig.get('status', 'PENDING')
            tag = 'success' if status in ('MATCHED', 'PLACED') else 'failed' if status == 'FAILED' else ''
            
            self.tg_signals_tree.insert('', tk.END, values=(
                timestamp,
                selection,
                side,
                f"{sig.get('parsed_odds', 0):.2f}" if sig.get('parsed_odds') else '',
                f"{sig.get('parsed_stake', 0):.2f}" if sig.get('parsed_stake') else '',
                status
            ), tags=(tag,) if tag else ())
    
    def _refresh_rules_tree(self):
        """Refresh signal patterns tree."""
        if not hasattr(self, 'rules_tree') or not self.rules_tree.winfo_exists():
            return
        self.rules_tree.delete(*self.rules_tree.get_children())
        patterns = self.db.get_signal_patterns()
        for p in patterns:
            enabled_str = 'Si' if p.get('enabled') else 'No'
            pattern_display = p.get('pattern', '')[:40]
            self.rules_tree.insert('', tk.END, iid=str(p['id']), values=(
                enabled_str,
                p.get('name', ''),
                p.get('market_type', ''),
                pattern_display
            ))
    
    def _add_signal_pattern(self):
        """Add a new signal pattern via inline form in the tab."""
        self._show_pattern_editor(mode='add')
    
    def _edit_signal_pattern(self):
        """Edit the selected signal pattern."""
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una regola da modificare")
            return
        pattern_id = int(selected[0])
        self._show_pattern_editor(mode='edit', pattern_id=pattern_id)
    
    def _delete_signal_pattern(self):
        """Delete the selected signal pattern."""
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una regola da eliminare")
            return
        
        pattern_id = int(selected[0])
        item = self.rules_tree.item(selected[0])
        pattern_name = item['values'][1]
        
        if messagebox.askyesno("Conferma", f"Eliminare la regola '{pattern_name}'?"):
            self.db.delete_signal_pattern(pattern_id)
            self._refresh_rules_tree()
            self._reload_listener_patterns()
    
    def _toggle_signal_pattern(self):
        """Toggle enable/disable for selected pattern."""
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una regola da attivare/disattivare")
            return
        
        pattern_id = int(selected[0])
        item = self.rules_tree.item(selected[0])
        current_enabled = item['values'][0] == 'Si'
        
        self.db.toggle_signal_pattern(pattern_id, not current_enabled)
        self._refresh_rules_tree()
        self._reload_listener_patterns()
    
    def _reload_listener_patterns(self):
        """Reload custom patterns in the Telegram listener if running."""
        if self.telegram_listener:
            try:
                self.telegram_listener.reload_custom_patterns()
            except Exception as e:
                print(f"[DEBUG] Error reloading listener patterns: {e}")
    
    def _show_pattern_editor(self, mode='add', pattern_id=None):
        """Show pattern editor in a sub-tab instead of popup."""
        if hasattr(self, 'pattern_editor_frame') and self.pattern_editor_frame.winfo_exists():
            self.pattern_editor_frame.destroy()
        
        existing_pattern = None
        if mode == 'edit' and pattern_id:
            patterns = self.db.get_signal_patterns()
            for p in patterns:
                if p['id'] == pattern_id:
                    existing_pattern = p
                    break
        
        self.pattern_editor_frame = ctk.CTkFrame(self.telegram_tab, fg_color=COLORS['bg_panel'], corner_radius=8)
        self.pattern_editor_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=0.7, relheight=0.7)
        
        header_frame = ctk.CTkFrame(self.pattern_editor_frame, fg_color='transparent')
        header_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        title_text = "Modifica Regola" if mode == 'edit' else "Nuova Regola di Parsing"
        ctk.CTkLabel(header_frame, text=title_text, font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(side=tk.LEFT)
        
        ctk.CTkButton(header_frame, text="X", width=30, height=30,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['loss'],
                      corner_radius=6, command=lambda: self.pattern_editor_frame.destroy()).pack(side=tk.RIGHT)
        
        form_frame = ctk.CTkFrame(self.pattern_editor_frame, fg_color='transparent')
        form_frame.pack(fill=tk.X, padx=15, pady=5)
        
        ctk.CTkLabel(form_frame, text="Nome:", text_color=COLORS['text_secondary']).grid(row=0, column=0, sticky=tk.W, pady=3)
        name_var = tk.StringVar(value=existing_pattern.get('name', '') if existing_pattern else '')
        ctk.CTkEntry(form_frame, textvariable=name_var, width=300,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).grid(row=0, column=1, pady=3, padx=5)
        
        ctk.CTkLabel(form_frame, text="Descrizione:", text_color=COLORS['text_secondary']).grid(row=1, column=0, sticky=tk.W, pady=3)
        desc_var = tk.StringVar(value=existing_pattern.get('description', '') if existing_pattern else '')
        ctk.CTkEntry(form_frame, textvariable=desc_var, width=300,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).grid(row=1, column=1, pady=3, padx=5)
        
        ctk.CTkLabel(form_frame, text="Pattern Predefinito:", text_color=COLORS['text_secondary']).grid(row=2, column=0, sticky=tk.W, pady=3)
        
        preset_patterns = {
            "-- Seleziona --": ("", "OVER_UNDER_X5"),
            "Over 0.5": ("over.*(0.5)", "OVER_UNDER_X5"),
            "Over 1.5": ("over.*(1.5)", "OVER_UNDER_X5"),
            "Over 2.5": ("over.*(2.5)", "OVER_UNDER_X5"),
            "Over 3.5": ("over.*(3.5)", "OVER_UNDER_X5"),
            "Under 0.5": ("under.*(0.5)", "OVER_UNDER_X5"),
            "Under 1.5": ("under.*(1.5)", "OVER_UNDER_X5"),
            "Under 2.5": ("under.*(2.5)", "OVER_UNDER_X5"),
            "Under 3.5": ("under.*(3.5)", "OVER_UNDER_X5"),
            "GG / BTTS": ("(gg|btts|gol)", "BOTH_TEAMS_TO_SCORE"),
            "NG / No Goal": ("(ng|no.?goal|nogol)", "BOTH_TEAMS_TO_SCORE"),
            "1T Over 0.5": ("1t.*(over|0.5)", "OVER_UNDER_15_FH"),
            "1T Under 0.5": ("1t.*(under|0.5)", "OVER_UNDER_15_FH"),
            "1X (Casa o Pari)": ("(1x)", "DOUBLE_CHANCE"),
            "X2 (Pari o Trasferta)": ("(x2)", "DOUBLE_CHANCE"),
            "12 (Casa o Trasferta)": ("(12)", "DOUBLE_CHANCE"),
            "Casa Vince": ("(home|casa|1)", "MATCH_ODDS"),
            "Pareggio": ("(draw|pari|x)", "MATCH_ODDS"),
            "Trasferta Vince": ("(away|trasferta|2)", "MATCH_ODDS"),
            "Personalizzato...": ("", "OVER_UNDER_X5"),
        }
        
        preset_var = tk.StringVar(value="-- Seleziona --")
        pattern_var = tk.StringVar(value=existing_pattern.get('pattern', '') if existing_pattern else '')
        market_types = ['OVER_UNDER_X5', 'BOTH_TEAMS_TO_SCORE', 'OVER_UNDER_15_FH', 'DOUBLE_CHANCE',
                        'MATCH_ODDS', 'CORRECT_SCORE', 'ASIAN_HANDICAP', 'DRAW_NO_BET', 'HALF_TIME_FULL_TIME']
        market_var = tk.StringVar(value=existing_pattern.get('market_type', market_types[0]) if existing_pattern else market_types[0])
        
        def on_preset_change(choice):
            if choice in preset_patterns and choice not in ["-- Seleziona --", "Personalizzato..."]:
                pattern, market = preset_patterns[choice]
                pattern_var.set(pattern)
                market_var.set(market)
                if not name_var.get():
                    name_var.set(choice)
        
        preset_menu = ctk.CTkOptionMenu(form_frame, variable=preset_var, values=list(preset_patterns.keys()),
                                        fg_color=COLORS['bg_card'], button_color=COLORS['success'],
                                        button_hover_color='#4caf50', width=200, command=on_preset_change)
        preset_menu.grid(row=2, column=1, pady=3, padx=5, sticky=tk.W)
        
        options_frame = ctk.CTkFrame(form_frame, fg_color='transparent')
        options_frame.grid(row=2, column=2, pady=3, padx=5, sticky=tk.W)
        
        lay_var = tk.BooleanVar(value=existing_pattern.get('bet_side', 'BACK') == 'LAY' if existing_pattern else False)
        ctk.CTkCheckBox(options_frame, text="LAY", variable=lay_var,
                        fg_color=COLORS['lay'], hover_color=COLORS['lay_hover'],
                        text_color=COLORS['text_primary'], width=60).pack(side=tk.LEFT, padx=(0, 10))
        
        live_var = tk.BooleanVar(value=bool(existing_pattern.get('live_only', 0)) if existing_pattern else False)
        ctk.CTkCheckBox(options_frame, text="LIVE", variable=live_var,
                        fg_color=COLORS['success'], hover_color='#4caf50',
                        text_color=COLORS['text_primary'], width=60).pack(side=tk.LEFT)
        
        ctk.CTkLabel(form_frame, text="Pattern Regex:", text_color=COLORS['text_secondary']).grid(row=3, column=0, sticky=tk.W, pady=3)
        ctk.CTkEntry(form_frame, textvariable=pattern_var, width=300,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).grid(row=3, column=1, pady=3, padx=5)
        
        ctk.CTkLabel(form_frame, text="Tipo Mercato:", text_color=COLORS['text_secondary']).grid(row=4, column=0, sticky=tk.W, pady=3)
        market_menu = ctk.CTkOptionMenu(form_frame, variable=market_var, values=market_types,
                                        fg_color=COLORS['bg_card'], button_color=COLORS['button_primary'],
                                        button_hover_color=COLORS['back_hover'], width=200)
        market_menu.grid(row=4, column=1, pady=3, padx=5, sticky=tk.W)
        
        enabled_var = tk.BooleanVar(value=existing_pattern.get('enabled', True) if existing_pattern else True)
        ctk.CTkCheckBox(form_frame, text="Regola Attiva", variable=enabled_var,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary']).grid(row=5, column=1, pady=10, sticky=tk.W)
        
        help_frame = ctk.CTkFrame(self.pattern_editor_frame, fg_color=COLORS['bg_card'], corner_radius=6)
        help_frame.pack(fill=tk.X, padx=15, pady=10)
        
        help_text = """Seleziona un pattern predefinito dal menu sopra, oppure scegli "Personalizzato" 
e scrivi il tuo pattern nel campo Pattern Regex."""
        ctk.CTkLabel(help_frame, text=help_text, font=('Segoe UI', 10),
                     text_color=COLORS['text_secondary'], justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=10)
        
        btn_frame = ctk.CTkFrame(self.pattern_editor_frame, fg_color='transparent')
        btn_frame.pack(fill=tk.X, padx=15, pady=15)
        
        def save_pattern():
            name = name_var.get().strip()
            pattern = pattern_var.get().strip()
            market = market_var.get()
            desc = desc_var.get().strip()
            enabled = enabled_var.get()
            bet_side = 'LAY' if lay_var.get() else 'BACK'
            live_only = live_var.get()
            
            if not name:
                messagebox.showwarning("Errore", "Inserisci un nome per la regola")
                return
            if not pattern:
                messagebox.showwarning("Errore", "Inserisci il pattern regex")
                return
            
            import re
            try:
                re.compile(pattern)
            except re.error as e:
                messagebox.showerror("Errore Regex", f"Pattern non valido: {e}")
                return
            
            if mode == 'edit' and pattern_id:
                self.db.update_signal_pattern(pattern_id, name=name, description=desc,
                                               pattern=pattern, market_type=market, enabled=enabled,
                                               bet_side=bet_side, live_only=live_only)
            else:
                self.db.save_signal_pattern(name, desc, pattern, market, enabled, bet_side=bet_side, live_only=live_only)
            
            self.pattern_editor_frame.destroy()
            self._refresh_rules_tree()
            self._reload_listener_patterns()
            messagebox.showinfo("Salvato", f"Regola '{name}' salvata con successo!")
        
        def cancel_edit():
            self.pattern_editor_frame.destroy()
        
        ctk.CTkButton(btn_frame, text="Salva", command=save_pattern,
                      fg_color=COLORS['button_success'], hover_color='#4caf50',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="Annulla", command=cancel_edit,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
    
    def _create_strumenti_tab(self):
        """Create Strumenti tab content."""
        main_frame = ctk.CTkFrame(self.strumenti_tab, fg_color='transparent')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Strumenti", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, pady=(0, 20))
        
        tools_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        tools_frame.pack(fill=tk.X, pady=10)
        
        ctk.CTkLabel(tools_frame, text="Strumenti di Trading", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15, pady=(15, 10))
        
        btn_frame1 = ctk.CTkFrame(tools_frame, fg_color='transparent')
        btn_frame1.pack(fill=tk.X, padx=15, pady=5)
        ctk.CTkButton(btn_frame1, text="Multi-Market Monitor", command=self._show_multi_market_monitor,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=180).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(btn_frame1, text="Monitora piu mercati contemporaneamente", 
                     font=('Segoe UI', 9), text_color=COLORS['text_secondary']).pack(side=tk.LEFT, padx=10)
        
        btn_frame2 = ctk.CTkFrame(tools_frame, fg_color='transparent')
        btn_frame2.pack(fill=tk.X, padx=15, pady=(5, 15))
        ctk.CTkButton(btn_frame2, text="Filtri Avanzati", command=self._show_advanced_filters,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=180).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(btn_frame2, text="Configura filtri per eventi e mercati", 
                     font=('Segoe UI', 9), text_color=COLORS['text_secondary']).pack(side=tk.LEFT, padx=10)
    
    def _create_plugin_tab(self):
        """Create Plugin tab content with install/uninstall/enable/disable functionality."""
        main_frame = ctk.CTkFrame(self.plugin_tab, fg_color='transparent')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        ctk.CTkLabel(header_frame, text="Gestione Plugin", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(side=tk.LEFT)
        
        # Install button
        ctk.CTkButton(header_frame, text="Installa Plugin", command=self._install_plugin,
                      fg_color=COLORS['success'], hover_color='#0ea271',
                      corner_radius=6, width=140).pack(side=tk.RIGHT, padx=5)
        
        # Reload all button
        ctk.CTkButton(header_frame, text="Ricarica Tutti", command=self._reload_all_plugins,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=120).pack(side=tk.RIGHT, padx=5)
        
        # Plugin list frame
        list_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        ctk.CTkLabel(list_frame, text="Plugin Installati", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15, pady=(15, 10))
        
        # Treeview for plugins
        tree_frame = ctk.CTkFrame(list_frame, fg_color='transparent')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        columns = ('name', 'version', 'author', 'status', 'description')
        self.plugins_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=10)
        
        self.plugins_tree.heading('name', text='Nome')
        self.plugins_tree.heading('version', text='Versione')
        self.plugins_tree.heading('author', text='Autore')
        self.plugins_tree.heading('status', text='Stato')
        self.plugins_tree.heading('description', text='Descrizione')
        
        self.plugins_tree.column('name', width=150)
        self.plugins_tree.column('version', width=70)
        self.plugins_tree.column('author', width=120)
        self.plugins_tree.column('status', width=100)
        self.plugins_tree.column('description', width=300)
        
        # Tags for status colors
        self.plugins_tree.tag_configure('enabled', foreground=COLORS['success'])
        self.plugins_tree.tag_configure('disabled', foreground=COLORS['text_secondary'])
        self.plugins_tree.tag_configure('error', foreground=COLORS['error'])
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.plugins_tree.yview)
        self.plugins_tree.configure(yscrollcommand=scrollbar.set)
        
        self.plugins_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Action buttons frame
        action_frame = ctk.CTkFrame(list_frame, fg_color='transparent')
        action_frame.pack(fill=tk.X, padx=15, pady=(5, 15))
        
        ctk.CTkButton(action_frame, text="Abilita", command=self._enable_selected_plugin,
                      fg_color=COLORS['success'], hover_color='#0ea271',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        
        ctk.CTkButton(action_frame, text="Disabilita", command=self._disable_selected_plugin,
                      fg_color=COLORS['warning'], hover_color='#d97706',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        
        ctk.CTkButton(action_frame, text="Disinstalla", command=self._uninstall_selected_plugin,
                      fg_color=COLORS['loss'], hover_color='#dc2626',
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        
        ctk.CTkButton(action_frame, text="Dettagli", command=self._show_plugin_details,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=100).pack(side=tk.LEFT, padx=5)
        
        # Security info frame
        security_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        security_frame.pack(fill=tk.X, pady=(10, 0))
        
        ctk.CTkLabel(security_frame, text="Sicurezza Plugin", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        security_info = """I plugin vengono eseguiti con le seguenti protezioni:
- Timeout: Max 10 secondi per operazione
- Thread separato: L'app rimane fluida anche se il plugin si blocca
- Sandbox: Accesso file limitato alle cartelle plugins e data
- Validazione: Funzioni pericolose bloccate (eval, exec, os.system, ecc.)
- Librerie: Solo librerie pre-approvate o installate via requirements.txt"""
        
        ctk.CTkLabel(security_frame, text=security_info, font=('Segoe UI', 10),
                     text_color=COLORS['text_secondary'], justify=tk.LEFT).pack(anchor=tk.W, padx=15, pady=(0, 15))
        
        # Plugin folder path
        folder_frame = ctk.CTkFrame(security_frame, fg_color='transparent')
        folder_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ctk.CTkLabel(folder_frame, text=f"Cartella plugin: {self.plugin_manager.plugins_dir}", 
                     font=('Segoe UI', 9), text_color=COLORS['text_secondary']).pack(side=tk.LEFT)
        
        ctk.CTkButton(folder_frame, text="Apri Cartella", command=self._open_plugins_folder,
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'],
                      corner_radius=6, width=100).pack(side=tk.RIGHT)
        
        # Load existing plugins
        self._load_plugins_on_startup()
        self._refresh_plugins_tree()
    
    def _load_plugins_on_startup(self):
        """Load all plugins from plugins folder on startup."""
        try:
            self.plugin_manager.load_all_plugins()
        except Exception as e:
            print(f"[Plugin] Errore caricamento plugin: {e}")
    
    def _refresh_plugins_tree(self):
        """Refresh the plugins treeview."""
        self.plugins_tree.delete(*self.plugins_tree.get_children())
        
        for plugin in self.plugin_manager.get_plugin_list():
            if plugin.error:
                status = 'Errore'
                tag = 'error'
            elif plugin.enabled:
                status = 'Abilitato'
                tag = 'enabled'
            else:
                status = 'Disabilitato'
                tag = 'disabled'
            
            self.plugins_tree.insert('', tk.END, values=(
                plugin.name,
                plugin.version,
                plugin.author,
                status,
                plugin.description[:50] + '...' if len(plugin.description) > 50 else plugin.description
            ), tags=(tag,))
    
    def _install_plugin(self):
        """Install a plugin from file."""
        filepath = filedialog.askopenfilename(
            title="Seleziona Plugin",
            filetypes=[("Python files", "*.py")],
            initialdir=str(self.plugin_manager.plugins_dir)
        )
        
        if not filepath:
            return
        
        success, msg = self.plugin_manager.install_plugin_from_file(filepath)
        if success:
            messagebox.showinfo("Plugin Installato", msg)
            self._refresh_plugins_tree()
        else:
            messagebox.showerror("Errore Installazione", msg)
    
    def _reload_all_plugins(self):
        """Reload all plugins."""
        # Unload all first
        for name in list(self.plugin_manager.plugins.keys()):
            self.plugin_manager.unload_plugin(name)
        
        # Reload
        self.plugin_manager.load_all_plugins()
        self._refresh_plugins_tree()
        messagebox.showinfo("Plugin", "Plugin ricaricati")
    
    def _get_selected_plugin_name(self):
        """Get the name of the selected plugin."""
        selection = self.plugins_tree.selection()
        if not selection:
            messagebox.showwarning("Seleziona Plugin", "Seleziona un plugin dalla lista")
            return None
        
        item = self.plugins_tree.item(selection[0])
        return item['values'][0]
    
    def _enable_selected_plugin(self):
        """Enable the selected plugin."""
        name = self._get_selected_plugin_name()
        if not name:
            return
        
        success, msg = self.plugin_manager.enable_plugin(name)
        if success:
            self._refresh_plugins_tree()
        else:
            messagebox.showerror("Errore", msg)
    
    def _disable_selected_plugin(self):
        """Disable the selected plugin."""
        name = self._get_selected_plugin_name()
        if not name:
            return
        
        success, msg = self.plugin_manager.disable_plugin(name)
        if success:
            self._refresh_plugins_tree()
        else:
            messagebox.showerror("Errore", msg)
    
    def _uninstall_selected_plugin(self):
        """Uninstall the selected plugin."""
        name = self._get_selected_plugin_name()
        if not name:
            return
        
        if not messagebox.askyesno("Conferma", f"Disinstallare il plugin '{name}'?"):
            return
        
        success, msg = self.plugin_manager.uninstall_plugin(name)
        if success:
            self._refresh_plugins_tree()
            messagebox.showinfo("Plugin Rimosso", msg)
        else:
            messagebox.showerror("Errore", msg)
    
    def _show_plugin_details(self):
        """Show details of the selected plugin."""
        name = self._get_selected_plugin_name()
        if not name:
            return
        
        if name not in self.plugin_manager.plugins:
            return
        
        plugin = self.plugin_manager.plugins[name]
        
        details = f"""Nome: {plugin.name}
Versione: {plugin.version}
Autore: {plugin.author}
Abilitato: {'Si' if plugin.enabled else 'No'}
Verificato: {'Si' if plugin.verified else 'No'}

Descrizione:
{plugin.description}

File: {plugin.path}
Tempo caricamento: {plugin.load_time:.2f}s
Esecuzioni: {plugin.execution_count}

Ultimo errore: {plugin.last_error or 'Nessuno'}"""
        
        messagebox.showinfo(f"Dettagli Plugin: {name}", details)
    
    def _open_plugins_folder(self):
        """Open the plugins folder in file explorer."""
        import subprocess
        try:
            subprocess.Popen(['explorer', str(self.plugin_manager.plugins_dir)])
        except:
            messagebox.showinfo("Cartella Plugin", str(self.plugin_manager.plugins_dir))
    
    def add_plugin_tab(self, title: str, create_func, plugin_name: str):
        """Add a tab created by a plugin."""
        pass
    
    def remove_plugin_tab(self, title: str, plugin_name: str):
        """Remove a tab created by a plugin."""
        pass
    
    def add_event_filter(self, name: str, filter_func, plugin_name: str):
        """Add a custom event filter from a plugin."""
        pass
    
    def _create_impostazioni_tab(self):
        """Create Impostazioni tab content with scrollbar."""
        canvas = tk.Canvas(self.impostazioni_tab, bg=COLORS['bg_dark'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.impostazioni_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ctk.CTkFrame(canvas, fg_color='transparent')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        main_frame = scrollable_frame
        
        ctk.CTkLabel(main_frame, text="Impostazioni", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=20, pady=(20, 20))
        
        cred_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        cred_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ctk.CTkLabel(cred_frame, text="Credenziali Betfair", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=15, pady=(15, 10))
        
        settings = self.db.get_settings() or {}
        
        ctk.CTkLabel(cred_frame, text="Username:", text_color=COLORS['text_secondary']).grid(row=1, column=0, sticky=tk.W, padx=15, pady=2)
        self.settings_username_var = tk.StringVar(value=settings.get('username', ''))
        ctk.CTkEntry(cred_frame, textvariable=self.settings_username_var, width=250,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).grid(row=1, column=1, pady=2, padx=5)
        
        ctk.CTkLabel(cred_frame, text="App Key:", text_color=COLORS['text_secondary']).grid(row=2, column=0, sticky=tk.W, padx=15, pady=2)
        self.settings_appkey_var = tk.StringVar(value=settings.get('app_key', ''))
        ctk.CTkEntry(cred_frame, textvariable=self.settings_appkey_var, width=320,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).grid(row=2, column=1, pady=2, padx=5)
        
        ctk.CTkLabel(cred_frame, text="Certificato (.crt):", text_color=COLORS['text_secondary']).grid(row=3, column=0, sticky=tk.W, padx=15, pady=2)
        self.settings_cert_var = tk.StringVar(value=settings.get('certificate', ''))
        cert_frame = ctk.CTkFrame(cred_frame, fg_color='transparent')
        cert_frame.grid(row=3, column=1, pady=2, padx=5, sticky=tk.W)
        ctk.CTkEntry(cert_frame, textvariable=self.settings_cert_var, width=280,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(side=tk.LEFT)
        ctk.CTkButton(cert_frame, text="...", width=30, command=lambda: self._browse_file(self.settings_cert_var, [("Certificati", "*.crt *.pem")]),
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'], corner_radius=6).pack(side=tk.LEFT, padx=2)
        
        ctk.CTkLabel(cred_frame, text="Chiave Privata (.key):", text_color=COLORS['text_secondary']).grid(row=4, column=0, sticky=tk.W, padx=15, pady=2)
        self.settings_key_var = tk.StringVar(value=settings.get('private_key', ''))
        key_frame = ctk.CTkFrame(cred_frame, fg_color='transparent')
        key_frame.grid(row=4, column=1, pady=2, padx=5, sticky=tk.W)
        ctk.CTkEntry(key_frame, textvariable=self.settings_key_var, width=280,
                     fg_color=COLORS['bg_card'], border_color=COLORS['border']).pack(side=tk.LEFT)
        ctk.CTkButton(key_frame, text="...", width=30, command=lambda: self._browse_file(self.settings_key_var, [("Chiavi", "*.key *.pem")]),
                      fg_color=COLORS['button_secondary'], hover_color=COLORS['bg_hover'], corner_radius=6).pack(side=tk.LEFT, padx=2)
        
        ctk.CTkButton(cred_frame, text="Salva Credenziali", command=self._save_settings_from_tab,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=150).grid(row=5, column=1, pady=(10, 15), sticky=tk.W, padx=5)
        
        update_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        update_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ctk.CTkLabel(update_frame, text="Aggiornamenti", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15, pady=(15, 10))
        
        self.auto_update_var = tk.BooleanVar(value=self.db.get_auto_update_enabled())
        ctk.CTkCheckBox(update_frame, text="Controlla automaticamente aggiornamenti all'avvio", 
                        variable=self.auto_update_var, command=self._save_auto_update_setting,
                        fg_color=COLORS['back'], hover_color=COLORS['back_hover'],
                        text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15)
        
        btn_update_frame = ctk.CTkFrame(update_frame, fg_color='transparent')
        btn_update_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        ctk.CTkButton(btn_update_frame, text="Verifica Aggiornamenti", command=self._check_for_updates_manual,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=180).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(btn_update_frame, text=f"Versione attuale: {APP_VERSION}", 
                     font=('Segoe UI', 9), text_color=COLORS['text_secondary']).pack(side=tk.LEFT, padx=10)
        
        app_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        app_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ctk.CTkLabel(app_frame, text="Applicazione", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=15, pady=(15, 10))
        
        ctk.CTkButton(app_frame, text="Esci dall'Applicazione", command=self._on_close,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=180).pack(anchor=tk.W, padx=15, pady=(0, 15))
    
    def _create_simulazione_tab(self):
        """Create Simulazione tab content."""
        main_frame = ctk.CTkFrame(self.simulazione_tab, fg_color='transparent')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Simulazione", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, pady=(0, 10))
        
        sim_settings = self.db.get_simulation_settings()
        balance = sim_settings.get('virtual_balance', 1000) if sim_settings else 1000
        starting = sim_settings.get('starting_balance', 1000) if sim_settings else 1000
        pl = balance - starting
        pl_text = f"+{pl:.2f}" if pl >= 0 else f"{pl:.2f}"
        pl_color = COLORS['success'] if pl >= 0 else COLORS['loss']
        
        stats_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        stats_frame.pack(fill=tk.X, pady=10)
        
        balance_card = ctk.CTkFrame(stats_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        balance_card.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ctk.CTkLabel(balance_card, text="Saldo Simulato", font=('Segoe UI', 9),
                     text_color=COLORS['text_secondary']).pack(pady=(10, 2))
        ctk.CTkLabel(balance_card, text=f"{balance:.2f} EUR", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(pady=(0, 10))
        
        pl_card = ctk.CTkFrame(stats_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        pl_card.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ctk.CTkLabel(pl_card, text="Profitto/Perdita", font=('Segoe UI', 9),
                     text_color=COLORS['text_secondary']).pack(pady=(10, 2))
        ctk.CTkLabel(pl_card, text=f"{pl_text} EUR", font=('Segoe UI', 14, 'bold'),
                     text_color=pl_color).pack(pady=(0, 10))
        
        starting_card = ctk.CTkFrame(stats_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        starting_card.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ctk.CTkLabel(starting_card, text="Saldo Iniziale", font=('Segoe UI', 9),
                     text_color=COLORS['text_secondary']).pack(pady=(10, 2))
        ctk.CTkLabel(starting_card, text=f"{starting:.2f} EUR", font=FONTS['title'],
                     text_color=COLORS['text_primary']).pack(pady=(0, 10))
        
        btn_frame = ctk.CTkFrame(main_frame, fg_color='transparent')
        btn_frame.pack(fill=tk.X, pady=10)
        ctk.CTkButton(btn_frame, text="Reset Simulazione", command=self._reset_simulation,
                      fg_color=COLORS['button_danger'], hover_color='#c62828',
                      corner_radius=6, width=150).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="Aggiorna", command=self._refresh_simulazione_tab,
                      fg_color=COLORS['button_primary'], hover_color=COLORS['back_hover'],
                      corner_radius=6, width=120).pack(side=tk.LEFT, padx=5)
        
        bets_frame = ctk.CTkFrame(main_frame, fg_color=COLORS['bg_panel'], corner_radius=8)
        bets_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ctk.CTkLabel(bets_frame, text="Storico Scommesse Simulate", font=FONTS['heading'],
                     text_color=COLORS['text_primary']).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        self.sim_bets_frame = bets_frame
        self._refresh_simulation_bets_list()
    
    def _refresh_simulazione_tab(self):
        """Refresh the Simulazione tab."""
        for widget in self.simulazione_tab.winfo_children():
            widget.destroy()
        self._create_simulazione_tab()
    
    def _refresh_simulation_bets_list(self):
        """Refresh the simulation bets list."""
        for widget in self.sim_bets_frame.winfo_children():
            widget.destroy()
        
        sim_bets = self.db.get_simulation_bets(limit=50)
        
        columns = ('data', 'evento', 'mercato', 'tipo', 'stake', 'profitto')
        tree = ttk.Treeview(self.sim_bets_frame, columns=columns, show='headings', height=15)
        tree.heading('data', text='Data')
        tree.heading('evento', text='Evento')
        tree.heading('mercato', text='Mercato')
        tree.heading('tipo', text='Tipo')
        tree.heading('stake', text='Stake')
        tree.heading('profitto', text='Profitto')
        tree.column('data', width=130)
        tree.column('evento', width=180)
        tree.column('mercato', width=120)
        tree.column('tipo', width=50)
        tree.column('stake', width=70)
        tree.column('profitto', width=80)
        
        tree.tag_configure('win', foreground=COLORS['success'])
        tree.tag_configure('loss', foreground=COLORS['loss'])
        
        scrollbar = ttk.Scrollbar(self.sim_bets_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if not sim_bets:
            ttk.Label(self.sim_bets_frame, text="Nessuna scommessa simulata", 
                     font=('Segoe UI', 10)).place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            return
        
        for bet in sim_bets:
            placed_at = bet.get('placed_at', '')[:16] if bet.get('placed_at') else ''
            event_name = bet.get('event_name', '')[:25]
            market_name = bet.get('market_name', '')[:20]
            bet_type = bet.get('bet_type', '')
            stake = bet.get('stake', 0)
            profit = bet.get('profit', 0) or 0
            
            tag = 'win' if profit > 0 else 'loss' if profit < 0 else ''
            profit_text = f"+{profit:.2f}" if profit > 0 else f"{profit:.2f}"
            
            tree.insert('', tk.END, values=(
                placed_at,
                event_name,
                market_name,
                bet_type,
                f"{stake:.2f}",
                profit_text
            ), tags=(tag,) if tag else ())
    
    def _save_settings_from_tab(self):
        """Save settings from Impostazioni tab."""
        self.db.save_credentials(
            username=self.settings_username_var.get(),
            app_key=self.settings_appkey_var.get(),
            certificate=self.settings_cert_var.get(),
            private_key=self.settings_key_var.get()
        )
        messagebox.showinfo("Salvato", "Credenziali salvate con successo")
    
    def _save_auto_update_setting(self):
        """Save auto-update setting."""
        self.db.set_auto_update_enabled(self.auto_update_var.get())
    
    def _browse_file(self, var, filetypes):
        """Open file browser and set variable."""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)
    
    def _show_dashboard(self):
        """Show dashboard with account info and bets."""
        if not self.client:
            messagebox.showwarning("Attenzione", "Devi prima connetterti")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Dashboard - Account Betfair Italy")
        dialog.geometry("800x700")
        dialog.transient(self.root)
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Panoramica del tuo account Betfair Italy", 
                 style='Title.TLabel').pack(anchor=tk.W, pady=(0, 20))
        
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=10)
        
        def create_stat_card(parent, title, value, subtitle, col):
            card = ttk.LabelFrame(parent, text=title, padding=10)
            card.grid(row=0, column=col, padx=5, sticky='nsew')
            ttk.Label(card, text=value, style='Title.TLabel').pack()
            ttk.Label(card, text=subtitle, font=('Segoe UI', 8)).pack()
            return card
        
        try:
            funds = self.client.get_account_funds()
            self.account_data = funds
        except:
            funds = self.account_data
        
        daily_pl = self.db.get_today_profit_loss()
        try:
            orders = self.client.get_current_orders()
            active_count = len([o for o in orders.get('matched', []) if o.get('sizeMatched', 0) > 0])
        except:
            active_count = self.db.get_active_bets_count()
        
        create_stat_card(stats_frame, "Saldo Disponibile", 
                        f"{funds.get('available', 0):.2f} EUR", 
                        "Fondi disponibili per scommettere", 0)
        create_stat_card(stats_frame, "Esposizione", 
                        f"{abs(funds.get('exposure', 0)):.2f} EUR", 
                        "Responsabilita corrente", 1)
        pl_text = f"+{daily_pl:.2f}" if daily_pl >= 0 else f"{daily_pl:.2f}"
        create_stat_card(stats_frame, "P/L Oggi", 
                        f"{pl_text} EUR", 
                        "Profitto/Perdita giornaliero", 2)
        create_stat_card(stats_frame, "Scommesse Attive", 
                        str(active_count), 
                        "In attesa di risultato", 3)
        
        for i in range(4):
            stats_frame.columnconfigure(i, weight=1)
        
        def refresh_dashboard():
            def fetch_data():
                try:
                    funds = self.client.get_account_funds()
                    self.account_data = funds
                    daily_pl = self.db.get_today_profit_loss()
                    try:
                        orders = self.client.get_current_orders()
                        active_count = len([o for o in orders.get('matched', []) if o.get('sizeMatched', 0) > 0])
                    except:
                        active_count = self.db.get_active_bets_count()
                    
                    self.uiq.post(update_ui, funds, daily_pl, active_count)
                except Exception as e:
                    err_msg = str(e)
                    self.uiq.post(messagebox.showerror, "Errore", err_msg)
            
            def update_ui(funds, daily_pl, active_count):
                if not dialog.winfo_exists():
                    return
                
                for widget in stats_frame.winfo_children():
                    widget.destroy()
                
                create_stat_card(stats_frame, "Saldo Disponibile", 
                                f"{funds.get('available', 0):.2f} EUR", 
                                "Fondi disponibili per scommettere", 0)
                create_stat_card(stats_frame, "Esposizione", 
                                f"{abs(funds.get('exposure', 0)):.2f} EUR", 
                                "Responsabilita corrente", 1)
                pl_text = f"+{daily_pl:.2f}" if daily_pl >= 0 else f"{daily_pl:.2f}"
                create_stat_card(stats_frame, "P/L Oggi", 
                                f"{pl_text} EUR", 
                                "Profitto/Perdita giornaliero", 2)
                create_stat_card(stats_frame, "Scommesse Attive", 
                                str(active_count), 
                                "In attesa di risultato", 3)
            
            self.executor.submit("refresh_dashboard_popup", fetch_data)
        
        ttk.Button(main_frame, text="Aggiorna", command=refresh_dashboard).pack(anchor=tk.E, pady=10)
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        recent_frame = ttk.Frame(notebook, padding=10)
        notebook.add(recent_frame, text="Scommesse Recenti")
        self._create_bets_list(recent_frame, self.db.get_recent_bets(20))
        
        orders_frame = ttk.Frame(notebook, padding=10)
        notebook.add(orders_frame, text="Ordini Correnti")
        self._create_current_orders_view(orders_frame)
        
        bookings_frame = ttk.Frame(notebook, padding=10)
        notebook.add(bookings_frame, text="Prenotazioni")
        self._create_bookings_view(bookings_frame)
        
        cashout_frame = ttk.Frame(notebook, padding=10)
        notebook.add(cashout_frame, text="Cashout")
        self._create_cashout_view(cashout_frame, dialog)
    
    def _create_settled_bets_list(self, parent, settled_bets):
        """Create a list view of settled bets from Betfair."""
        columns = ('data', 'mercato', 'selezione', 'tipo', 'stake', 'profitto')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=12)
        tree.heading('data', text='Data')
        tree.heading('mercato', text='Market ID')
        tree.heading('selezione', text='Selezione')
        tree.heading('tipo', text='Tipo')
        tree.heading('stake', text='Stake')
        tree.heading('profitto', text='Profitto')
        tree.column('data', width=130)
        tree.column('mercato', width=140)
        tree.column('selezione', width=100)
        tree.column('tipo', width=50)
        tree.column('stake', width=70)
        tree.column('profitto', width=80)
        
        tree.tag_configure('win', foreground=COLORS['success'])
        tree.tag_configure('loss', foreground=COLORS['loss'])
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if not settled_bets:
            ttk.Label(parent, text="Nessuna scommessa negli ultimi 7 giorni", 
                     font=('Segoe UI', 10)).place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            return
        
        for bet in settled_bets:
            settled_date = bet.get('settledDate', '')[:16].replace('T', ' ') if bet.get('settledDate') else ''
            market_id = bet.get('marketId', '')
            selection_id = str(bet.get('selectionId', ''))
            side = bet.get('side', '')
            stake = bet.get('size', 0)
            profit = bet.get('profit', 0)
            
            tag = 'win' if profit > 0 else 'loss' if profit < 0 else ''
            profit_text = f"+{profit:.2f}" if profit > 0 else f"{profit:.2f}"
            
            tree.insert('', tk.END, values=(
                settled_date,
                market_id,
                selection_id,
                side,
                f"{stake:.2f}",
                profit_text
            ), tags=(tag,))
    
    def _create_bets_list(self, parent, bets):
        """Create a list view of bets with status colors."""
        columns = ('data', 'evento', 'mercato', 'tipo', 'stake', 'profitto', 'stato')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=12)
        tree.heading('data', text='Data')
        tree.heading('evento', text='Evento')
        tree.heading('mercato', text='Mercato')
        tree.heading('tipo', text='Tipo')
        tree.heading('stake', text='Stake')
        tree.heading('profitto', text='Prof. Atteso')
        tree.heading('stato', text='Stato')
        tree.column('data', width=100)
        tree.column('evento', width=140)
        tree.column('mercato', width=110)
        tree.column('tipo', width=50)
        tree.column('stake', width=70)
        tree.column('profitto', width=70)
        tree.column('stato', width=80)
        
        tree.tag_configure('matched', foreground=COLORS['matched'])
        tree.tag_configure('pending', foreground=COLORS['pending'])
        tree.tag_configure('partially_matched', foreground=COLORS['partially_matched'])
        tree.tag_configure('settled', foreground=COLORS['settled'])
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if not bets:
            ttk.Label(parent, text="Nessuna scommessa recente", font=('Segoe UI', 10)).pack(pady=20)
        
        for bet in bets:
            placed_at = bet.get('placed_at', '')[:16] if bet.get('placed_at') else ''
            status = bet.get('status', '')
            profit = bet.get('potential_profit', 0)
            profit_display = f"+{profit:.2f}" if profit else "-"
            
            status_lower = status.lower().replace(' ', '_')
            tag = status_lower if status_lower in ('matched', 'pending', 'partially_matched', 'settled') else ''
            
            tree.insert('', tk.END, values=(
                placed_at,
                bet.get('event_name', '')[:25],
                bet.get('market_name', '')[:18],
                bet.get('side', bet.get('bet_type', '')),
                f"{bet.get('stake', bet.get('total_stake', 0)):.2f}",
                profit_display,
                status
            ), tags=(tag,) if tag else ())
    
    def _create_current_orders_view(self, parent):
        """Create view for current orders from Betfair."""
        if not self.client:
            ttk.Label(parent, text="Non connesso").pack()
            return
        
        sub_notebook = ttk.Notebook(parent)
        sub_notebook.pack(fill=tk.BOTH, expand=True)
        
        try:
            orders = self.client.get_current_orders()
        except:
            orders = {'matched': [], 'unmatched': [], 'partiallyMatched': []}
        
        matched_frame = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(matched_frame, text=f"Abbinate ({len(orders['matched'])})")
        self._create_orders_list(matched_frame, orders['matched'])
        
        unmatched_frame = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(unmatched_frame, text=f"Non Abbinate ({len(orders['unmatched'])})")
        self._create_orders_list(unmatched_frame, orders['unmatched'], show_cancel=True)
        
        partial_frame = ttk.Frame(sub_notebook, padding=5)
        sub_notebook.add(partial_frame, text=f"Parziali ({len(orders['partiallyMatched'])})")
        self._create_orders_list(partial_frame, orders['partiallyMatched'])
    
    def _create_orders_list(self, parent, orders, show_cancel=False):
        """Create list of orders."""
        columns = ('mercato', 'tipo', 'quota', 'stake', 'abbinato')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=8)
        tree.heading('mercato', text='Mercato')
        tree.heading('tipo', text='Tipo')
        tree.heading('quota', text='Quota')
        tree.heading('stake', text='Stake')
        tree.heading('abbinato', text='Abbinato')
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        for order in orders:
            tree.insert('', tk.END, iid=order.get('betId'), values=(
                order.get('marketId', '')[:15],
                order.get('side', ''),
                f"{order.get('price', 0):.2f}",
                f"{order.get('size', 0):.2f}",
                f"{order.get('sizeMatched', 0):.2f}"
            ))
        
        if show_cancel and orders:
            def cancel_selected():
                selected = tree.selection()
                if selected and self.client:
                    for bet_id in selected:
                        item = tree.item(bet_id)
                        market_id = item['values'][0] if item['values'] else None
                        if market_id:
                            try:
                                self.client.cancel_orders(market_id, [bet_id])
                            except:
                                pass
                    messagebox.showinfo("Info", "Ordini cancellati")
            
            ttk.Button(parent, text="Cancella Selezionati", command=cancel_selected).pack(pady=5)
    
    def _create_bookings_view(self, parent):
        """Create view for bet bookings."""
        bookings = self.db.get_pending_bookings()
        
        columns = ('runner', 'quota_target', 'stake', 'tipo', 'stato')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=8)
        tree.heading('runner', text='Selezione')
        tree.heading('quota_target', text='Quota Target')
        tree.heading('stake', text='Stake')
        tree.heading('tipo', text='Tipo')
        tree.heading('stato', text='Stato')
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        for booking in bookings:
            tree.insert('', tk.END, iid=str(booking['id']), values=(
                booking.get('runner_name', '')[:20],
                f"{booking.get('target_price', 0):.2f}",
                f"{booking.get('stake', 0):.2f}",
                booking.get('side', ''),
                booking.get('status', '')
            ))
        
        def cancel_booking():
            selected = tree.selection()
            for bid in selected:
                self.db.cancel_booking(int(bid))
            messagebox.showinfo("Info", "Prenotazioni cancellate")
            for item in tree.get_children():
                tree.delete(item)
            for booking in self.db.get_pending_bookings():
                tree.insert('', tk.END, iid=str(booking['id']), values=(
                    booking.get('runner_name', '')[:20],
                    f"{booking.get('target_price', 0):.2f}",
                    f"{booking.get('stake', 0):.2f}",
                    booking.get('side', ''),
                    booking.get('status', '')
                ))
        
        ttk.Button(parent, text="Cancella Prenotazione", command=cancel_booking).pack(pady=5)
        ttk.Label(parent, text="Le prenotazioni verranno attivate quando la quota raggiunge il target").pack()
    
    def _create_cashout_view(self, parent, dialog):
        """Create cashout view with positions and cashout buttons."""
        if not self.client:
            ttk.Label(parent, text="Non connesso a Betfair").pack()
            return
        
        ttk.Label(parent, text="Posizioni Aperte con Cashout", style='Title.TLabel').pack(anchor=tk.W, pady=(0, 10))
        
        columns = ('mercato', 'selezione', 'tipo', 'quota', 'stake', 'p/l_attuale', 'azione')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=10)
        tree.heading('mercato', text='Mercato')
        tree.heading('selezione', text='Selezione')
        tree.heading('tipo', text='Tipo')
        tree.heading('quota', text='Quota')
        tree.heading('stake', text='Stake')
        tree.heading('p/l_attuale', text='P/L Attuale')
        tree.heading('azione', text='Azione')
        tree.column('mercato', width=100)
        tree.column('selezione', width=100)
        tree.column('tipo', width=50)
        tree.column('quota', width=60)
        tree.column('stake', width=60)
        tree.column('p/l_attuale', width=80)
        tree.column('azione', width=80)
        
        tree.tag_configure('profit', foreground=COLORS['success'])
        tree.tag_configure('loss', foreground=COLORS['loss'])
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        positions_data = {}
        no_positions_label = [None]
        
        def load_positions():
            if no_positions_label[0]:
                no_positions_label[0].destroy()
                no_positions_label[0] = None
            
            def fetch():
                try:
                    orders = self.client.get_current_orders()
                    matched = orders.get('matched', [])
                    
                    self.uiq.post(process_matched, matched)
                except Exception as e:
                    err_msg = str(e)
                    self.uiq.post(messagebox.showerror, "Errore", f"Impossibile caricare posizioni: {err_msg}")
            
            def process_matched(matched):
                for item in tree.get_children():
                    tree.delete(item)
                positions_data.clear()
                
                for order in matched:
                    market_id = order.get('marketId')
                    selection_id = order.get('selectionId')
                    side = order.get('side')
                    price = order.get('price', 0)
                    stake = order.get('sizeMatched', 0)
                    
                    if stake > 0:
                        try:
                            cashout_info = self.client.calculate_cashout(
                                market_id, selection_id, side, stake, price
                            )
                            green_up = cashout_info.get('green_up', 0)
                            pl_display = f"{green_up:+.2f}"
                            pl_tag = 'profit' if green_up > 0 else 'loss'
                        except:
                            cashout_info = None
                            pl_display = "N/D"
                            pl_tag = None
                        
                        item_id = f"{order.get('betId')}"
                        tags = (pl_tag,) if pl_tag else ()
                        tree.insert('', tk.END, iid=item_id, values=(
                            market_id[:12] if market_id else '',
                            order.get('runnerName', str(selection_id))[:15],
                            side,
                            f"{price:.2f}",
                            f"{stake:.2f}",
                            pl_display,
                            "Cashout"
                        ), tags=tags)
                        
                        positions_data[item_id] = {
                            'market_id': market_id,
                            'selection_id': selection_id,
                            'side': side,
                            'price': price,
                            'stake': stake,
                            'cashout_info': cashout_info
                        }
                
                if not positions_data:
                    no_positions_label[0] = ttk.Label(parent, text="Nessuna posizione aperta al momento", 
                              font=('Segoe UI', 10))
                    no_positions_label[0].pack(anchor=tk.W, pady=5)
                    cashout_btn.config(state='disabled')
                else:
                    cashout_btn.config(state='normal')
            
            self.executor.submit("load_cashout_positions", fetch)
        
        def do_cashout():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Attenzione", "Seleziona una posizione")
                return
            
            for item_id in selected:
                pos = positions_data.get(item_id)
                if not pos or not pos.get('cashout_info'):
                    continue
                
                info = pos['cashout_info']
                confirm = messagebox.askyesno(
                    "Conferma Cashout",
                    f"Eseguire cashout?\n\n"
                    f"Tipo: {info['cashout_side']} @ {info['current_price']:.2f}\n"
                    f"Stake: {info['cashout_stake']:.2f}\n"
                    f"Profitto garantito: {info['green_up']:+.2f}"
                )
                
                if confirm:
                    try:
                        result = self.client.execute_cashout(
                            pos['market_id'],
                            pos['selection_id'],
                            info['cashout_side'],
                            info['cashout_stake'],
                            info['current_price']
                        )
                        
                        if result.get('status') == 'SUCCESS':
                            self.db.save_cashout_transaction(
                                market_id=pos['market_id'],
                                selection_id=pos['selection_id'],
                                original_bet_id=item_id,
                                cashout_bet_id=result.get('betId'),
                                original_side=pos['side'],
                                original_stake=pos['stake'],
                                original_price=pos['price'],
                                cashout_side=info['cashout_side'],
                                cashout_stake=info['cashout_stake'],
                                cashout_price=result.get('averagePriceMatched') or info['current_price'],
                                profit_loss=info['green_up']
                            )
                            messagebox.showinfo("Successo", f"Cashout eseguito!\nProfitto bloccato: {info['green_up']:+.2f}")
                            load_positions()
                            self._update_balance()
                        elif result.get('status') == 'ERROR':
                            messagebox.showerror("Errore", f"Cashout fallito: {result.get('error', 'Errore sconosciuto')}")
                        else:
                            messagebox.showerror("Errore", f"Cashout fallito: {result.get('status')}")
                    except Exception as e:
                        err_msg = str(e)
                        messagebox.showerror("Errore", f"Errore cashout: {err_msg}")
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="Aggiorna Posizioni", command=load_positions).pack(side=tk.LEFT, padx=5)
        
        cashout_btn = tk.Button(btn_frame, text="CASHOUT", bg='#28a745', fg='white', 
                                font=('Segoe UI', 10, 'bold'), command=do_cashout)
        cashout_btn.pack(side=tk.LEFT, padx=5)
        
        live_tracking_var = tk.BooleanVar(value=True)
        live_tracking_id = [None]
        
        def toggle_live_tracking():
            if live_tracking_var.get():
                start_live_tracking()
            else:
                stop_live_tracking()
        
        def start_live_tracking():
            def update_pl():
                if not live_tracking_var.get():
                    return
                try:
                    load_positions()
                except:
                    pass
                live_tracking_id[0] = parent.after(5000, update_pl)
            
            live_tracking_id[0] = parent.after(5000, update_pl)
            live_status_label.config(text="LIVE", foreground='#28a745')
        
        def stop_live_tracking():
            if live_tracking_id[0]:
                parent.after_cancel(live_tracking_id[0])
                live_tracking_id[0] = None
            live_status_label.config(text="", foreground='gray')
        
        ttk.Checkbutton(btn_frame, text="Live Tracking", variable=live_tracking_var,
                        command=toggle_live_tracking).pack(side=tk.LEFT, padx=15)
        
        live_status_label = ttk.Label(btn_frame, text="", font=('Segoe UI', 9, 'bold'))
        live_status_label.pack(side=tk.LEFT)
        
        def on_close():
            stop_live_tracking()
            dialog.destroy()
        
        dialog.protocol("WM_DELETE_WINDOW", on_close)
        
        auto_frame = ttk.LabelFrame(parent, text="Auto-Cashout", padding=10)
        auto_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(auto_frame, text="Target Profitto:").grid(row=0, column=0, padx=5)
        profit_target = ttk.Entry(auto_frame, width=10)
        profit_target.insert(0, "10.00")
        profit_target.grid(row=0, column=1, padx=5)
        
        ttk.Label(auto_frame, text="Limite Perdita:").grid(row=0, column=2, padx=5)
        loss_limit = ttk.Entry(auto_frame, width=10)
        loss_limit.insert(0, "-5.00")
        loss_limit.grid(row=0, column=3, padx=5)
        
        def set_auto_cashout():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Attenzione", "Seleziona una posizione")
                return
            
            try:
                target = float(profit_target.get())
                limit = float(loss_limit.get())
            except:
                messagebox.showerror("Errore", "Valori non validi")
                return
            
            for item_id in selected:
                pos = positions_data.get(item_id)
                if pos:
                    self.db.save_auto_cashout_rule(
                        pos['market_id'],
                        item_id,
                        target,
                        limit
                    )
            
            messagebox.showinfo("Info", "Auto-cashout impostato")
        
        ttk.Button(auto_frame, text="Imposta Auto-Cashout", command=set_auto_cashout).grid(row=0, column=4, padx=10)
        
        ttk.Label(parent, text="Auto-cashout esegue automaticamente quando P/L raggiunge target o limite",
                  font=('Segoe UI', 8)).pack(anchor=tk.W)
        
        load_positions()
        start_live_tracking()
    
    def _show_multi_market_monitor(self):
        """Show multi-market monitor window."""
        if not self.client:
            messagebox.showwarning("Attenzione", "Connettiti prima a Betfair")
            return
        
        monitor = tk.Toplevel(self.root)
        monitor.title("Multi-Market Monitor")
        monitor.geometry("1000x600")
        monitor.transient(self.root)
        
        if not hasattr(self, 'watchlist'):
            self.watchlist = []
        
        main_frame = ttk.Frame(monitor, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(control_frame, text="Aggiungi mercato corrente alla watchlist:").pack(side=tk.LEFT)
        
        def add_current_market():
            if self.current_market and self.current_event:
                market_info = {
                    'event_id': self.current_event['id'],
                    'event_name': self.current_event['name'],
                    'market_id': self.current_market['marketId'],
                    'market_name': self.current_market.get('marketName', 'N/A'),
                    'runners': self.current_market.get('runners', [])
                }
                for m in self.watchlist:
                    if m['market_id'] == market_info['market_id']:
                        messagebox.showinfo("Info", "Mercato già nella watchlist")
                        return
                self.watchlist.append(market_info)
                refresh_watchlist()
                messagebox.showinfo("Aggiunto", f"Aggiunto: {market_info['event_name']}")
            else:
                messagebox.showwarning("Attenzione", "Seleziona prima un mercato")
        
        ttk.Button(control_frame, text="+ Aggiungi Corrente", command=add_current_market).pack(side=tk.LEFT, padx=10)
        
        monitor_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="Auto-refresh (30s)", variable=monitor_refresh_var).pack(side=tk.LEFT, padx=10)
        
        def remove_selected():
            selection = watchlist_tree.selection()
            if selection:
                idx = watchlist_tree.index(selection[0])