import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from auto_updater import DEFAULT_UPDATE_URL, check_for_updates, show_update_dialog
from betfair_client import MARKET_TYPES
from theme import COLORS, FONTS, configure_ttk_dark_theme

APP_NAME = "Pickfair"
APP_VERSION = "3.19.1"


class UIModule:
    def _try_maximize(self):
        try:
            self.root.state("zoomed")
        except:
            pass

    def _configure_styles(self):
        style = ttk.Style()
        configure_ttk_dark_theme(style)

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="Configura Credenziali", command=self._show_credentials_dialog
        )
        file_menu.add_command(
            label="Configura Aggiornamenti", command=self._show_update_settings_dialog
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Verifica Aggiornamenti", command=self._check_for_updates_manual
        )
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self._on_close)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Strumenti", menu=tools_menu)
        tools_menu.add_command(
            label="Multi-Market Monitor", command=self._show_multi_market_monitor
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Reset Simulazione", command=self._reset_simulation
        )

        telegram_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Telegram", menu=telegram_menu)
        telegram_menu.add_command(
            label="Avvia Listener", command=self._start_telegram_listener
        )
        telegram_menu.add_command(
            label="Ferma Listener", command=self._stop_telegram_listener
        )

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aiuto", menu=help_menu)
        help_menu.add_command(label="Informazioni", command=self._show_about)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._stop_auto_refresh()
        try:
            if self.telegram_listener:
                self.telegram_listener.stop()
            self.shutdown_mgr.shutdown()
        except:
            pass
        if self.client:
            try:
                self.client.logout()
            except:
                pass
        self.root.destroy()
        import sys

        sys.exit(0)

    def _create_main_layout(self):
        self.main_frame = ctk.CTkFrame(self.root, fg_color=COLORS["bg_dark"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._create_status_bar()
        self.main_notebook = ctk.CTkTabview(
            self.main_frame,
            fg_color=COLORS["bg_surface"],
            segmented_button_fg_color=COLORS["bg_panel"],
            segmented_button_selected_color=COLORS["back"],
            segmented_button_unselected_color=COLORS["bg_panel"],
            text_color=COLORS["text_primary"],
        )
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
        status_frame = ctk.CTkFrame(
            self.main_frame, fg_color=COLORS["bg_panel"], corner_radius=8, height=50
        )
        status_frame.pack(fill=tk.X, pady=(0, 10))
        status_frame.pack_propagate(False)
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Non connesso",
            text_color=COLORS["error"],
            font=FONTS["default"],
        )
        self.status_label.pack(side=tk.LEFT, padx=15)
        self.balance_label = ctk.CTkLabel(
            status_frame,
            text="",
            text_color=COLORS["back"],
            font=("Segoe UI", 12, "bold"),
        )
        self.balance_label.pack(side=tk.LEFT, padx=20)
        self.stream_label = ctk.CTkLabel(
            status_frame, text="", text_color=COLORS["warning"], font=FONTS["default"]
        )
        self.stream_label.pack(side=tk.LEFT, padx=10)
        self.connect_btn = ctk.CTkButton(
            status_frame,
            text="Connetti",
            command=self._toggle_connection,
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["back_hover"],
            corner_radius=6,
            width=100,
        )
        self.connect_btn.pack(side=tk.RIGHT, padx=10)
        self.refresh_btn = ctk.CTkButton(
            status_frame,
            text="Aggiorna",
            command=self._refresh_data,
            state=tk.DISABLED,
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["back_hover"],
            corner_radius=6,
            width=100,
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=5)
        self.live_btn = ctk.CTkButton(
            status_frame,
            text="LIVE",
            fg_color=COLORS["loss"],
            hover_color="#c62828",
            command=self._toggle_live_mode,
            corner_radius=6,
            width=80,
        )
        self.live_btn.pack(side=tk.RIGHT, padx=5)
        self.sim_btn = ctk.CTkButton(
            status_frame,
            text="SIMULAZIONE",
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["bg_hover"],
            command=self._toggle_simulation_mode,
            corner_radius=6,
            width=120,
        )
        self.sim_btn.pack(side=tk.RIGHT, padx=5)
        self.sim_balance_label = ctk.CTkLabel(
            status_frame, text="", text_color="#9c27b0", font=("Segoe UI", 11, "bold")
        )
        self.sim_balance_label.pack(side=tk.LEFT, padx=10)

    def _create_events_panel(self, parent):
        events_frame = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_panel"], corner_radius=8
        )
        events_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        ctk.CTkLabel(
            events_frame,
            text="Partite",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(10, 5))
        search_frame = ctk.CTkFrame(events_frame, fg_color="transparent")
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_events)
        ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="Cerca partita...",
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
        ).pack(fill=tk.X)
        auto_refresh_frame = ctk.CTkFrame(events_frame, fg_color="transparent")
        auto_refresh_frame.pack(fill=tk.X, padx=10, pady=(5, 5))
        self.auto_refresh_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            auto_refresh_frame,
            text="Auto-refresh ogni",
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh,
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            text_color=COLORS["text_primary"],
        ).pack(side=tk.LEFT)
        self.auto_refresh_interval_var = tk.StringVar(value="30")
        ctk.CTkOptionMenu(
            auto_refresh_frame,
            variable=self.auto_refresh_interval_var,
            values=["15", "30", "60", "120", "300"],
            width=60,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["back"],
            button_hover_color=COLORS["back_hover"],
            command=lambda v: self._on_auto_refresh_interval_change(None),
        ).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(
            auto_refresh_frame, text="sec", text_color=COLORS["text_secondary"]
        ).pack(side=tk.LEFT)
        self.auto_refresh_status = ctk.CTkLabel(
            auto_refresh_frame, text="", text_color=COLORS["success"]
        )
        self.auto_refresh_status.pack(side=tk.LEFT, padx=10)
        tree_container = ctk.CTkFrame(events_frame, fg_color="transparent")
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.events_tree = ttk.Treeview(
            tree_container, columns=("name", "date"), show="tree headings", height=20
        )
        self.events_tree.heading("#0", text="Nazione")
        self.events_tree.heading("name", text="Partita")
        self.events_tree.heading("date", text="Data")
        self.events_tree.column("#0", width=80, minwidth=60)
        self.events_tree.column("name", width=150, minwidth=100)
        self.events_tree.column("date", width=70, minwidth=60)
        scrollbar = ttk.Scrollbar(
            tree_container, orient=tk.VERTICAL, command=self.events_tree.yview
        )
        self.events_tree.configure(yscrollcommand=scrollbar.set)
        self.events_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.events_tree.bind("<<TreeviewSelect>>", self._on_event_selected)
        self.all_events = []
        self.auto_refresh_id = None

    def _create_market_panel(self, parent):
        market_frame = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_panel"], corner_radius=8
        )
        market_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        ctk.CTkLabel(
            market_frame,
            text="Mercato",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(10, 5))
        header_frame = ctk.CTkFrame(market_frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.event_name_label = ctk.CTkLabel(
            header_frame,
            text="Seleziona una partita",
            font=("Segoe UI", 12, "bold"),
            text_color=COLORS["text_primary"],
        )
        self.event_name_label.pack(anchor=tk.W)
        selector_frame = ctk.CTkFrame(market_frame, fg_color="transparent")
        selector_frame.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(
            selector_frame, text="Tipo Mercato:", text_color=COLORS["text_secondary"]
        ).pack(side=tk.LEFT)
        self.market_type_var = tk.StringVar()
        self.market_combo = ctk.CTkOptionMenu(
            selector_frame,
            variable=self.market_type_var,
            values=[""],
            width=200,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["back"],
            button_hover_color=COLORS["back_hover"],
            command=lambda v: self._on_market_type_selected(None),
        )
        self.market_combo.pack(side=tk.LEFT, padx=5)
        stream_frame = ctk.CTkFrame(market_frame, fg_color="transparent")
        stream_frame.pack(fill=tk.X, padx=10, pady=5)
        self.stream_var = tk.BooleanVar(value=False)
        self.stream_check = ctk.CTkCheckBox(
            stream_frame,
            text="Streaming Quote Live",
            variable=self.stream_var,
            command=self._toggle_streaming,
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            text_color=COLORS["text_primary"],
        )
        self.stream_check.pack(side=tk.LEFT)
        self.dutch_modal_btn = ctk.CTkButton(
            stream_frame,
            text="Dutching Avanzato",
            fg_color=COLORS["info"],
            hover_color=COLORS["info_hover"],
            command=(
                self._show_dutching_modal
                if hasattr(self, "_show_dutching_modal")
                else lambda: None
            ),
            state=tk.DISABLED,
            corner_radius=6,
            width=130,
        )
        self.dutch_modal_btn.pack(side=tk.LEFT, padx=5)
        self.market_status_label = ctk.CTkLabel(
            stream_frame, text="", font=("Segoe UI", 9, "bold")
        )
        self.market_status_label.pack(side=tk.RIGHT, padx=10)
        runners_container = ctk.CTkFrame(market_frame, fg_color="transparent")
        runners_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.runners_tree = ttk.Treeview(
            runners_container,
            columns=("select", "name", "back", "back_size", "lay", "lay_size"),
            show="headings",
            height=18,
        )
        self.runners_tree.heading("select", text="")
        self.runners_tree.heading("name", text="Selezione")
        self.runners_tree.heading("back", text="Back")
        self.runners_tree.heading("back_size", text="Disp.")
        self.runners_tree.heading("lay", text="Lay")
        self.runners_tree.heading("lay_size", text="Disp.")
        self.runners_tree.column("select", width=30)
        self.runners_tree.column("name", width=120)
        self.runners_tree.column("back", width=60)
        self.runners_tree.column("back_size", width=60)
        self.runners_tree.column("lay", width=60)
        self.runners_tree.column("lay_size", width=60)
        self.runners_tree.tag_configure("runner_row", background=COLORS["bg_card"])
        scrollbar = ttk.Scrollbar(
            runners_container, orient=tk.VERTICAL, command=self.runners_tree.yview
        )
        self.runners_tree.configure(yscrollcommand=scrollbar.set)
        self.runners_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.runners_tree.bind("<ButtonRelease-1>", self._on_runner_clicked)
        self.runners_tree.bind("<Button-3>", self._show_runner_context_menu)
        self.runners_tree.tag_configure(
            "clickable_back", foreground=COLORS["clickable_back"]
        )
        self.runners_tree.tag_configure(
            "clickable_lay", foreground=COLORS["clickable_lay"]
        )
        self.runner_context_menu = tk.Menu(self.root, tearoff=0)
        self.runner_context_menu.add_command(
            label="Prenota Scommessa", command=self._book_selected_runner
        )
        self.runner_context_menu.add_separator()
        self.runner_context_menu.add_command(
            label="Seleziona per Dutching", command=lambda: None
        )

    def _create_dutching_panel(self, parent):
        dutch_outer = ctk.CTkFrame(parent, fg_color=COLORS["bg_panel"], corner_radius=8)
        dutch_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        ctk.CTkLabel(
            dutch_outer,
            text="Calcolo Dutching",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(10, 5))
        canvas = tk.Canvas(dutch_outer, highlightthickness=0, bg=COLORS["bg_panel"])
        scrollbar = ttk.Scrollbar(dutch_outer, orient=tk.VERTICAL, command=canvas.yview)
        dutch_frame = ctk.CTkFrame(canvas, fg_color="transparent")
        dutch_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=dutch_frame, anchor="nw")
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width)
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        type_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        type_frame.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(
            type_frame, text="Tipo:", text_color=COLORS["text_secondary"]
        ).pack(side=tk.LEFT)
        self.bet_type_var = tk.StringVar(value="BACK")
        self.back_btn = ctk.CTkButton(
            type_frame,
            text="Back",
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            corner_radius=6,
            width=80,
            command=lambda: self._set_bet_type("BACK"),
        )
        self.back_btn.pack(side=tk.LEFT, padx=5)
        self.lay_btn = ctk.CTkButton(
            type_frame,
            text="Lay",
            fg_color=COLORS["lay"],
            hover_color=COLORS["lay_hover"],
            corner_radius=6,
            width=80,
            command=lambda: self._set_bet_type("LAY"),
        )
        self.lay_btn.pack(side=tk.LEFT)
        stake_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        stake_frame.pack(fill=tk.X, padx=10, pady=5)
        ctk.CTkLabel(
            stake_frame, text="Stake Totale (EUR):", text_color=COLORS["text_secondary"]
        ).pack(side=tk.LEFT)
        self.stake_var = tk.StringVar(value="1.00")
        self.stake_var.trace_add("write", lambda *args: self._recalculate())
        ctk.CTkEntry(
            stake_frame,
            textvariable=self.stake_var,
            width=80,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
        ).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(
            stake_frame,
            text="(min. 1 EUR per selezione)",
            font=("Segoe UI", 8),
            text_color=COLORS["text_tertiary"],
        ).pack(side=tk.LEFT, padx=5)
        options_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        options_frame.pack(fill=tk.X, padx=10, pady=5)
        self.best_price_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_frame,
            text="Accetta Miglior Prezzo",
            variable=self.best_price_var,
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            text_color=COLORS["text_primary"],
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            options_frame,
            text="(piazza al prezzo corrente)",
            font=("Segoe UI", 8),
            text_color=COLORS["text_tertiary"],
        ).pack(side=tk.LEFT, padx=5)
        ctk.CTkLabel(
            dutch_frame,
            text="Selezioni:",
            font=("Segoe UI", 11, "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(10, 5))
        self.selections_text = ctk.CTkTextbox(
            dutch_frame,
            height=100,
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
        )
        self.selections_text.pack(fill=tk.BOTH, expand=True, padx=10)
        self.selections_text.configure(state=tk.DISABLED)
        ctk.CTkLabel(
            dutch_frame,
            text="Scommesse Piazzate:",
            font=("Segoe UI", 11, "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(10, 2))
        self.placed_bets_tree = ttk.Treeview(
            dutch_frame,
            columns=("sel", "tipo", "quota", "stake"),
            show="headings",
            height=4,
        )
        self.placed_bets_tree.heading("sel", text="Selezione")
        self.placed_bets_tree.heading("tipo", text="Tipo")
        self.placed_bets_tree.heading("quota", text="Quota")
        self.placed_bets_tree.heading("stake", text="Stake")
        self.placed_bets_tree.column("sel", width=100)
        self.placed_bets_tree.column("tipo", width=40)
        self.placed_bets_tree.column("quota", width=50)
        self.placed_bets_tree.column("stake", width=50)
        self.placed_bets_tree.tag_configure("back", foreground=COLORS["back"])
        self.placed_bets_tree.tag_configure("lay", foreground=COLORS["lay"])
        self.placed_bets_tree.pack(fill=tk.X, padx=10, pady=2)
        summary_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        summary_frame.pack(fill=tk.X, padx=10, pady=10)
        self.profit_label = ctk.CTkLabel(
            summary_frame,
            text="Profitto: -",
            font=("Segoe UI", 11, "bold"),
            text_color=COLORS["text_primary"],
        )
        self.profit_label.pack(anchor=tk.W)
        self.prob_label = ctk.CTkLabel(
            summary_frame,
            text="Probabilita Implicita: -",
            text_color=COLORS["text_secondary"],
        )
        self.prob_label.pack(anchor=tk.W)
        btn_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ctk.CTkButton(
            btn_frame,
            text="Cancella Selezioni",
            command=self._clear_selections,
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["bg_hover"],
            corner_radius=6,
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            btn_frame,
            text="Dutching Pro",
            command=self._open_dutching_window,
            fg_color=COLORS["info"],
            hover_color=COLORS["info_hover"],
            corner_radius=6,
            width=100,
        ).pack(side=tk.LEFT, padx=10)
        self.place_btn = ctk.CTkButton(
            btn_frame,
            text="Piazza Scommesse",
            command=self._place_bets,
            state=tk.DISABLED,
            fg_color=COLORS["button_success"],
            hover_color="#4caf50",
            corner_radius=6,
        )
        self.place_btn.pack(side=tk.RIGHT)
        separator = ctk.CTkFrame(dutch_frame, fg_color=COLORS["border"], height=2)
        separator.pack(fill=tk.X, padx=10, pady=10)
        ctk.CTkLabel(
            dutch_frame,
            text="Cashout",
            font=("Segoe UI", 11, "bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, padx=10, pady=(5, 2))
        self.market_cashout_tree = ttk.Treeview(
            dutch_frame, columns=("sel", "tipo", "p/l"), show="headings", height=4
        )
        self.market_cashout_tree.heading("sel", text="Selezione")
        self.market_cashout_tree.heading("tipo", text="Tipo")
        self.market_cashout_tree.heading("p/l", text="P/L")
        self.market_cashout_tree.column("sel", width=80)
        self.market_cashout_tree.column("tipo", width=40)
        self.market_cashout_tree.column("p/l", width=60)
        self.market_cashout_tree.tag_configure("profit", foreground=COLORS["success"])
        self.market_cashout_tree.tag_configure("loss", foreground=COLORS["loss"])
        self.market_cashout_tree.pack(fill=tk.X, padx=10, pady=2)
        cashout_btn_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        cashout_btn_frame.pack(fill=tk.X, padx=10, pady=5)
        self.market_cashout_btn = ctk.CTkButton(
            cashout_btn_frame,
            text="CASHOUT",
            fg_color=COLORS["success"],
            hover_color="#0d9668",
            font=("Segoe UI", 9, "bold"),
            state=tk.DISABLED,
            corner_radius=6,
            width=100,
            command=self._do_market_cashout,
        )
        self.market_cashout_btn.pack(side=tk.LEFT, padx=2)
        self.auto_cashout_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            cashout_btn_frame,
            text="Auto",
            variable=self.auto_cashout_var,
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            text_color=COLORS["text_primary"],
            width=60,
        ).pack(side=tk.LEFT, padx=5)
        self.market_live_tracking_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            cashout_btn_frame,
            text="Live",
            variable=self.market_live_tracking_var,
            command=self._toggle_market_live_tracking,
            fg_color=COLORS["success"],
            hover_color="#4caf50",
            text_color=COLORS["text_primary"],
            width=60,
        ).pack(side=tk.LEFT, padx=5)
        self.market_live_status = ctk.CTkLabel(
            cashout_btn_frame,
            text="",
            font=("Segoe UI", 8, "bold"),
            text_color=COLORS["text_secondary"],
        )
        self.market_live_status.pack(side=tk.LEFT)
        ctk.CTkButton(
            cashout_btn_frame,
            text="Aggiorna",
            command=self._update_market_cashout_positions,
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["bg_hover"],
            corner_radius=6,
            width=80,
        ).pack(side=tk.RIGHT, padx=2)
        self.market_cashout_tree.bind("<Double-1>", self._do_single_cashout)
        self.market_live_tracking_id = None
        self.market_cashout_fetch_in_progress = False
        self.market_cashout_fetch_cancelled = False
        self.market_cashout_positions = {}

    def _show_about(self):

        messagebox.showinfo(
            "Informazioni",
            f"{APP_NAME}\nVersione {APP_VERSION}\n\nApplicazione per dutching su Betfair Exchange Italia.\n\nMercati supportati:\n"
            + "\n".join([f"- {v}" for k, v in list(MARKET_TYPES.items())[:8]])
            + "\n...e altri\n\nDatabase:\n{get_db_path()}\n\nRequisiti:\n- Account Betfair Italia\n- Certificato SSL per API\n- App Key Betfair",
        )

    def _check_for_updates_on_startup(self):
        settings = self.db.get_settings() or {}
        update_url = settings.get("update_url") or DEFAULT_UPDATE_URL
        if not update_url:
            return
        skipped_version = settings.get("skipped_version")

        def on_update_result(result):
            if result.get("update_available") and (
                not skipped_version
                or result.get("latest_version", "") != skipped_version
            ):
                self.root.after(
                    100, lambda: self.uiq.post(self._show_update_notification, result)
                )

        check_for_updates(APP_VERSION, callback=on_update_result, update_url=update_url)

    def _show_update_notification(self, update_info):
        choice = show_update_dialog(self.root, update_info)
        if choice == "skip":
            self.db.save_skipped_version(update_info.get("latest_version"))

    def _check_for_updates_manual(self):
        settings = self.db.get_settings() or {}
        update_url = settings.get("update_url") or DEFAULT_UPDATE_URL
        if not update_url:
            return messagebox.showinfo(
                "Aggiornamenti",
                "Nessun URL di aggiornamento configurato.\n\nVai su File > Configura Aggiornamenti per impostarlo.",
            )

        def on_result(result):
            if result.get("update_available"):
                self.uiq.post(self._show_update_notification, result)
            elif result.get("error"):
                self.uiq.post(
                    messagebox.showerror,
                    "Errore",
                    f"Impossibile verificare aggiornamenti:\n{result.get('error')}",
                )
            else:
                self.uiq.post(
                    messagebox.showinfo,
                    "Aggiornamenti",
                    f"Hai gia' l'ultima versione ({APP_VERSION})!",
                )

        check_for_updates(APP_VERSION, callback=on_result, update_url=update_url)

    def _show_update_settings_dialog(self):

        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Aggiornamenti")
        dialog.geometry("500x250")
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame, text="Configura Aggiornamenti Automatici", style="Title.TLabel"
        ).pack(pady=(0, 15))
        settings = self.db.get_settings() or {}
        ttk.Label(frame, text="URL GitHub Releases API:").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text=f"(Default: {DEFAULT_UPDATE_URL})",
            foreground="gray",
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W)
        url_var = tk.StringVar(
            value=settings.get("update_url", "") or DEFAULT_UPDATE_URL
        )
        ttk.Entry(frame, textvariable=url_var, width=60).pack(fill=tk.X, pady=(5, 15))
        ttk.Label(
            frame,
            text="L'app controllera' automaticamente gli aggiornamenti all'avvio.",
            foreground="gray",
        ).pack(anchor=tk.W)

        def save():
            self.db.save_update_url(url_var.get().strip())
            self.db.save_skipped_version(None)
            dialog.destroy()
            messagebox.showinfo("Salvato", "Impostazioni aggiornamento salvate!")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=15)
        ttk.Button(btn_frame, text="Salva", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annulla", command=dialog.destroy).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            btn_frame,
            text="Verifica Ora",
            command=lambda: [dialog.destroy(), self._check_for_updates_manual()],
        ).pack(side=tk.RIGHT, padx=5)

    def _load_settings(self):
        settings = self.db.get_settings()
        if settings and settings.get("session_token"):
            self._try_restore_session(settings)

    def _try_restore_session(self, settings):
        if not all(
            [
                settings.get("username"),
                settings.get("app_key"),
                settings.get("certificate"),
                settings.get("private_key"),
            ]
        ):
            return
        expiry = settings.get("session_expiry")
        if expiry:
            try:
                if datetime.now() < datetime.fromisoformat(expiry):
                    self.status_label.configure(
                        text="Sessione salvata (clicca Connetti)",
                        text_color=COLORS["text_secondary"],
                    )
            except:
                pass

    def _show_credentials_dialog(self):
        from tkinter import scrolledtext

        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Credenziali Betfair")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        settings = self.db.get_settings() or {}
        ttk.Label(frame, text="Username Betfair:").pack(anchor=tk.W)
        username_var = tk.StringVar(value=settings.get("username", ""))
        ttk.Entry(frame, textvariable=username_var, width=50).pack(
            fill=tk.X, pady=(0, 10)
        )
        ttk.Label(frame, text="App Key:").pack(anchor=tk.W)
        appkey_var = tk.StringVar(value=settings.get("app_key", ""))
        ttk.Entry(frame, textvariable=appkey_var, width=50).pack(
            fill=tk.X, pady=(0, 10)
        )
        ttk.Label(frame, text="Certificato SSL (.pem):").pack(anchor=tk.W)
        cert_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        cert_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get("certificate"):
            cert_text.insert("1.0", settings["certificate"])
        ttk.Button(
            frame,
            text="Carica da file...",
            command=lambda: [
                cert_text.delete("1.0", tk.END),
                (
                    cert_text.insert("1.0", open(f, "r").read())
                    if (f := filedialog.askopenfilename())
                    else None
                ),
            ],
        ).pack(anchor=tk.W, pady=(0, 10))
        ttk.Label(frame, text="Chiave Privata (.key o .pem):").pack(anchor=tk.W)
        key_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        key_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get("private_key"):
            key_text.insert("1.0", settings["private_key"])
        ttk.Button(
            frame,
            text="Carica da file...",
            command=lambda: [
                key_text.delete("1.0", tk.END),
                (
                    key_text.insert("1.0", open(f, "r").read())
                    if (f := filedialog.askopenfilename())
                    else None
                ),
            ],
        ).pack(anchor=tk.W, pady=(0, 20))
        ttk.Button(
            frame,
            text="Salva",
            command=lambda: [
                self.db.save_credentials(
                    username_var.get(),
                    appkey_var.get(),
                    cert_text.get("1.0", tk.END).strip(),
                    key_text.get("1.0", tk.END).strip(),
                ),
                messagebox.showinfo("Salvato", "Credenziali salvate"),
                dialog.destroy(),
            ],
        ).pack(pady=10)

    def _browse_file(self, var, filetypes):

        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)

    def _create_dashboard_tab(self):
        main_frame = ctk.CTkFrame(self.dashboard_tab, fg_color="transparent")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        ctk.CTkLabel(
            main_frame,
            text="Dashboard - Account Betfair Italy",
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 20))
        self.dashboard_stats_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.dashboard_stats_frame.pack(fill=tk.X, pady=10)
        self.dashboard_not_connected = ctk.CTkLabel(
            main_frame,
            text="Connettiti a Betfair per vedere i dati",
            font=("Segoe UI", 11),
            text_color=COLORS["text_secondary"],
        )
        self.dashboard_not_connected.pack(pady=20)
        ctk.CTkButton(
            main_frame,
            text="Aggiorna Dashboard",
            command=self._refresh_dashboard_tab,
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["back_hover"],
            corner_radius=6,
        ).pack(anchor=tk.E, pady=10)
        self.dashboard_notebook = ctk.CTkTabview(
            main_frame,
            fg_color=COLORS["bg_panel"],
            segmented_button_fg_color=COLORS["bg_card"],
            segmented_button_selected_color=COLORS["back"],
            segmented_button_unselected_color=COLORS["bg_card"],
        )
        self.dashboard_notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        self.dashboard_notebook.add("Scommesse Recenti")
        self.dashboard_notebook.add("Ordini Correnti")
        self.dashboard_notebook.add("Prenotazioni")
        self.dashboard_notebook.add("Cashout")
        self.dashboard_recent_frame = self.dashboard_notebook.tab("Scommesse Recenti")
        self.dashboard_orders_frame = self.dashboard_notebook.tab("Ordini Correnti")
        self.dashboard_bookings_frame = self.dashboard_notebook.tab("Prenotazioni")
        self.dashboard_cashout_frame = self.dashboard_notebook.tab("Cashout")

    def _create_simulation_bets_list(self, parent):
        sim_bets = self.db.get_simulation_bets(limit=50)
        sim_settings = self.db.get_simulation_settings()
        if sim_settings:
            balance = sim_settings.get("virtual_balance", 1000)
            starting = sim_settings.get("starting_balance", 1000)
            pl = balance - starting
            info_frame = ttk.Frame(parent)
            info_frame.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(
                info_frame,
                text=f"Saldo Simulato: {balance:.2f} EUR",
                font=("Segoe UI", 10, "bold"),
            ).pack(side=tk.LEFT)
            ttk.Label(
                info_frame,
                text=f"  |  P/L: {('+'+str(round(pl,2))) if pl >= 0 else round(pl,2)} EUR",
                foreground="#28a745" if pl >= 0 else "#dc3545",
            ).pack(side=tk.LEFT)
        tree = ttk.Treeview(
            parent,
            columns=("data", "evento", "mercato", "tipo", "stake", "profitto"),
            show="headings",
            height=12,
        )
        tree.heading("data", text="Data")
        tree.heading("evento", text="Evento")
        tree.heading("mercato", text="Mercato")
        tree.heading("tipo", text="Tipo")
        tree.heading("stake", text="Stake")
        tree.heading("profitto", text="Profitto")
        tree.column("data", width=100)
        tree.column("evento", width=150)
        tree.column("mercato", width=120)
        tree.column("tipo", width=50)
        tree.column("stake", width=70)
        tree.column("profitto", width=80)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        if not sim_bets:
            ttk.Label(
                parent, text="Nessuna scommessa simulata", font=("Segoe UI", 10)
            ).pack(pady=20)
        for bet in sim_bets:
            tree.insert(
                "",
                tk.END,
                values=(
                    bet.get("placed_at", "")[:16] if bet.get("placed_at") else "",
                    bet.get("event_name", "")[:25],
                    bet.get("market_name", "")[:20],
                    bet.get("side", ""),
                    f"{bet.get('total_stake', 0):.2f}",
                    (
                        f"+{bet.get('potential_profit', 0):.2f}"
                        if (bet.get("potential_profit") or 0) > 0
                        else f"{bet.get('potential_profit', 0):.2f}"
                    ),
                ),
            )

    def _show_multi_market_monitor(self):
        if not self.client:
            return messagebox.showwarning("Attenzione", "Connettiti prima a Betfair")
        monitor = tk.Toplevel(self.root)
        monitor.title("Multi-Market Monitor")
        monitor.geometry("1000x600")
        monitor.transient(self.root)
        if not hasattr(self, "watchlist"):
            self.watchlist = []
        main_frame = ttk.Frame(monitor, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(control_frame, text="Aggiungi mercato corrente alla watchlist:").pack(
            side=tk.LEFT
        )

        def add_current_market():
            if self.current_market and self.current_event:
                market_info = {
                    "event_id": self.current_event["id"],
                    "event_name": self.current_event["name"],
                    "market_id": self.current_market["marketId"],
                    "market_name": self.current_market.get("marketName", "N/A"),
                    "runners": self.current_market.get("runners", []),
                }
                for m in self.watchlist:
                    if m["market_id"] == market_info["market_id"]:
                        return messagebox.showinfo(
                            "Info", "Mercato già nella watchlist"
                        )
                self.watchlist.append(market_info)
                messagebox.showinfo(
                    "Aggiunto", f"Aggiunto: {market_info['event_name']}"
                )
            else:
                messagebox.showwarning("Attenzione", "Seleziona prima un mercato")

        ttk.Button(
            control_frame, text="+ Aggiungi Corrente", command=add_current_market
        ).pack(side=tk.LEFT, padx=10)
        monitor_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            control_frame, text="Auto-refresh (30s)", variable=monitor_refresh_var
        ).pack(side=tk.LEFT, padx=10)
