import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from ui.tk_safe import tk, filedialog, messagebox, scrolledtext, ttk

import customtkinter as ctk

from auto_updater import DEFAULT_UPDATE_URL, check_for_updates, show_update_dialog
from betfair_client import MARKET_TYPES
from theme import COLORS, FONTS, configure_ttk_dark_theme

APP_NAME = "Pickfair"
APP_VERSION = "3.19.1"


class UIModule:
    # =========================================================
    # CORE HELPERS
    # =========================================================

    def _safe_get_db_settings(self) -> Dict[str, Any]:
        try:
            if hasattr(self, "db") and self.db and hasattr(self.db, "get_settings"):
                data = self.db.get_settings()
                return data or {}
        except Exception:
            pass
        return {}

    def _safe_message(self, kind: str, title: str, text: str):
        try:
            if kind == "info":
                messagebox.showinfo(title, text)
            elif kind == "warning":
                messagebox.showwarning(title, text)
            else:
                messagebox.showerror(title, text)
        except Exception:
            pass

    def _run_ui_safe(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def _tree_clear(self, tree):
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

    def _safe_after_cancel(self, attr_name: str):
        try:
            after_id = getattr(self, attr_name, None)
            if after_id and hasattr(self, "root") and self.root:
                self.root.after_cancel(after_id)
        except Exception:
            pass
        finally:
            try:
                setattr(self, attr_name, None)
            except Exception:
                pass

    def _parse_float(self, value, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return float(default)
            return float(str(value).replace(",", "."))
        except Exception:
            return float(default)

    def _parse_int(self, value, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return int(default)
            return int(value)
        except Exception:
            return int(default)

    # =========================================================
    # WINDOW / STYLE
    # =========================================================

    def _try_maximize(self):
        try:
            self.root.state("zoomed")
        except Exception:
            pass

    def _configure_styles(self):
        try:
            style = ttk.Style()
            configure_ttk_dark_theme(style)
        except Exception:
            pass

    # =========================================================
    # MENU
    # =========================================================

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="Configura Credenziali",
            command=self._show_credentials_dialog,
        )
        file_menu.add_command(
            label="Configura Aggiornamenti",
            command=self._show_update_settings_dialog,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Verifica Aggiornamenti",
            command=self._check_for_updates_manual,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self._on_close)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Strumenti", menu=tools_menu)
        tools_menu.add_command(
            label="Multi-Market Monitor",
            command=self._show_multi_market_monitor,
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Reset Simulazione",
            command=self._reset_simulation,
        )

        telegram_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Telegram", menu=telegram_menu)
        telegram_menu.add_command(
            label="Avvia Listener",
            command=self._start_telegram_listener,
        )
        telegram_menu.add_command(
            label="Ferma Listener",
            command=self._stop_telegram_listener,
        )

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aiuto", menu=help_menu)
        help_menu.add_command(label="Informazioni", command=self._show_about)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            self._stop_auto_refresh()
        except Exception:
            pass

        try:
            if getattr(self, "telegram_listener", None):
                self.telegram_listener.stop()
        except Exception:
            pass

        try:
            if getattr(self, "shutdown_mgr", None):
                self.shutdown_mgr.shutdown()
        except Exception:
            pass

        try:
            if getattr(self, "client", None):
                self.client.logout()
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass

        try:
            sys.exit(0)
        except Exception:
            pass

    # =========================================================
    # MAIN LAYOUT
    # =========================================================

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

        for tab in [
            "Trading",
            "Dashboard",
            "Telegram",
            "Strumenti",
            "Plugin",
            "Impostazioni",
            "Simulazione",
        ]:
            self.main_notebook.add(tab)

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
            self.main_frame,
            fg_color=COLORS["bg_panel"],
            corner_radius=8,
            height=50,
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
            status_frame,
            text="",
            text_color=COLORS["warning"],
            font=FONTS["default"],
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
            status_frame,
            text="",
            text_color="#9c27b0",
            font=("Segoe UI", 11, "bold"),
        )
        self.sim_balance_label.pack(side=tk.LEFT, padx=10)

    # =========================================================
    # EVENTS PANEL
    # =========================================================

    def _create_events_panel(self, parent):
        events_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_panel"], corner_radius=8)
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
            auto_refresh_frame,
            text="sec",
            text_color=COLORS["text_secondary"],
        ).pack(side=tk.LEFT)

        self.auto_refresh_status = ctk.CTkLabel(
            auto_refresh_frame,
            text="",
            text_color=COLORS["success"],
        )
        self.auto_refresh_status.pack(side=tk.LEFT, padx=10)

        tree_container = ctk.CTkFrame(events_frame, fg_color="transparent")
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.events_tree = ttk.Treeview(
            tree_container,
            columns=("name", "date"),
            show="tree headings",
            height=20,
        )
        self.events_tree.heading("#0", text="Nazione")
        self.events_tree.heading("name", text="Partita")
        self.events_tree.heading("date", text="Data")
        self.events_tree.column("#0", width=80, minwidth=60)
        self.events_tree.column("name", width=150, minwidth=100)
        self.events_tree.column("date", width=70, minwidth=60)

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.events_tree.yview)
        self.events_tree.configure(yscrollcommand=scrollbar.set)
        self.events_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.events_tree.bind("<<TreeviewSelect>>", self._on_event_selected)

        self.all_events: List[Dict[str, Any]] = []
        self.filtered_events: List[Dict[str, Any]] = []
        self.auto_refresh_id = None

    def _filter_events(self, *args):
        query = ""
        try:
            query = (self.search_var.get() or "").strip().lower()
        except Exception:
            pass

        if not query:
            self.filtered_events = list(self.all_events)
        else:
            self.filtered_events = [
                e for e in self.all_events
                if query in str(e.get("name", "")).lower()
                or query in str(e.get("country", "")).lower()
                or query in str(e.get("competition", "")).lower()
            ]
        self._refresh_events_tree()

    def _refresh_events_tree(self):
        self._tree_clear(self.events_tree)

        events = self.filtered_events if hasattr(self, "filtered_events") else self.all_events
        grouped: Dict[str, List[Dict[str, Any]]] = {}

        for event in events or []:
            country = str(event.get("country") or "N/A")
            grouped.setdefault(country, []).append(event)

        for country, rows in grouped.items():
            parent_id = self.events_tree.insert("", tk.END, text=country, values=("", ""))
            for ev in rows:
                event_id = str(ev.get("id", ""))
                self.events_tree.insert(
                    parent_id,
                    tk.END,
                    iid=event_id if event_id else None,
                    text="",
                    values=(
                        ev.get("name", ""),
                        ev.get("date", "")[:16] if ev.get("date") else "",
                    ),
                )

    def _toggle_auto_refresh(self):
        if bool(self.auto_refresh_var.get()):
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    def _start_auto_refresh(self):
        self._stop_auto_refresh()

        interval_ms = self._parse_int(getattr(self, "auto_refresh_interval_var", None).get() if hasattr(self, "auto_refresh_interval_var") else 30, 30) * 1000

        try:
            self.auto_refresh_status.configure(text="ON")
        except Exception:
            pass

        def _tick():
            try:
                if hasattr(self, "_load_events"):
                    self._load_events()
            except Exception:
                pass

            try:
                if hasattr(self, "root") and self.root and self.auto_refresh_var.get():
                    self.auto_refresh_id = self.root.after(interval_ms, _tick)
            except Exception:
                self.auto_refresh_id = None

        try:
            if hasattr(self, "root") and self.root and self.auto_refresh_var.get():
                self.auto_refresh_id = self.root.after(interval_ms, _tick)
        except Exception:
            self.auto_refresh_id = None

    def _stop_auto_refresh(self):
        self._safe_after_cancel("auto_refresh_id")
        try:
            if hasattr(self, "auto_refresh_status"):
                self.auto_refresh_status.configure(text="OFF")
        except Exception:
            pass

    def _on_auto_refresh_interval_change(self, event=None):
        if getattr(self, "auto_refresh_var", None) and self.auto_refresh_var.get():
            self._start_auto_refresh()

    def _on_event_selected(self, event=None):
        try:
            selected = self.events_tree.selection()
            if not selected:
                return

            item_id = selected[0]
            if self.events_tree.parent(item_id) == "":
                return

            event_id = item_id
            found = None
            for e in self.all_events:
                if str(e.get("id")) == str(event_id):
                    found = e
                    break

            if not found:
                return

            self.current_event = found
            try:
                self.event_name_label.configure(text=found.get("name", "Evento"))
            except Exception:
                pass

            if hasattr(self, "_load_markets_for_event"):
                self._load_markets_for_event(found)
            elif hasattr(self, "client") and self.client and hasattr(self.client, "get_available_markets"):
                try:
                    self.available_markets = self.client.get_available_markets(found["id"]) or []
                    values = [m.get("marketName", "") for m in self.available_markets]
                    if not values:
                        values = [""]
                    self.market_combo.configure(values=values)
                    if values and values[0]:
                        self.market_type_var.set(values[0])
                except Exception:
                    pass
        except Exception:
            pass

    # =========================================================
    # MARKET PANEL
    # =========================================================

    def _create_market_panel(self, parent):
        market_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_panel"], corner_radius=8)
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
            selector_frame,
            text="Tipo Mercato:",
            text_color=COLORS["text_secondary"],
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
            command=self._show_dutching_modal if hasattr(self, "_show_dutching_modal") else lambda: None,
            state=tk.DISABLED,
            corner_radius=6,
            width=130,
        )
        self.dutch_modal_btn.pack(side=tk.LEFT, padx=5)

        self.market_status_label = ctk.CTkLabel(
            stream_frame,
            text="",
            font=("Segoe UI", 9, "bold"),
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
        self.runners_tree.tag_configure("clickable_back", foreground=COLORS["clickable_back"])
        self.runners_tree.tag_configure("clickable_lay", foreground=COLORS["clickable_lay"])

        scrollbar = ttk.Scrollbar(runners_container, orient=tk.VERTICAL, command=self.runners_tree.yview)
        self.runners_tree.configure(yscrollcommand=scrollbar.set)
        self.runners_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.runners_tree.bind("<ButtonRelease-1>", self._on_runner_clicked)
        self.runners_tree.bind("<Button-3>", self._show_runner_context_menu)

        self.runner_context_menu = tk.Menu(self.root, tearoff=0)
        self.runner_context_menu.add_command(
            label="Prenota Scommessa",
            command=self._book_selected_runner,
        )
        self.runner_context_menu.add_separator()
        self.runner_context_menu.add_command(
            label="Seleziona per Dutching",
            command=lambda: None,
        )

    def _on_market_type_selected(self, event=None):
        market_name = ""
        try:
            market_name = self.market_type_var.get()
        except Exception:
            return

        if not market_name:
            return

        selected_market = None
        for m in getattr(self, "available_markets", []) or []:
            if m.get("marketName") == market_name:
                selected_market = m
                break

        if not selected_market:
            return

        self.current_market = selected_market

        try:
            if hasattr(self, "dutch_modal_btn"):
                self.dutch_modal_btn.configure(state=tk.NORMAL)
        except Exception:
            pass

        self._load_runners_for_current_market()

    def _load_runners_for_current_market(self):
        self._tree_clear(self.runners_tree)

        market = getattr(self, "current_market", None)
        if not market:
            return

        runners = market.get("runners", []) or []
        for r in runners:
            selection_id = str(r.get("selectionId", ""))
            name = r.get("runnerName", f"Runner {selection_id}")
            back = r.get("backPrice", r.get("price", "-"))
            lay = r.get("layPrice", "-")
            back_size = r.get("backSize", "-")
            lay_size = r.get("laySize", "-")

            try:
                self.runners_tree.insert(
                    "",
                    tk.END,
                    iid=selection_id if selection_id else None,
                    values=(
                        "",
                        name,
                        back,
                        back_size,
                        lay,
                        lay_size,
                    ),
                    tags=("runner_row",),
                )
            except Exception:
                pass

    def _toggle_streaming(self):
        enabled = bool(self.stream_var.get())
        try:
            if enabled and hasattr(self, "_start_streaming"):
                self._start_streaming()
            elif not enabled and hasattr(self, "_stop_streaming"):
                self._stop_streaming()
        except Exception as e:
            self._safe_message("error", "Streaming", f"Errore streaming:\n{e}")

    def _on_runner_clicked(self, event=None):
        try:
            item_id = self.runners_tree.focus()
            if not item_id:
                return

            item = self.runners_tree.item(item_id)
            values = item.get("values", [])
            if len(values) < 6:
                return

            runner_name = values[1]
            back_price = self._parse_float(values[2], 0.0)
            lay_price = self._parse_float(values[4], 0.0)

            if not hasattr(self, "selected_runners"):
                self.selected_runners = {}

            side = "BACK"
            price = back_price if back_price > 0 else lay_price
            if getattr(self, "bet_type_var", None):
                side = self.bet_type_var.get()
                if side == "LAY" and lay_price > 0:
                    price = lay_price

            self.selected_runners[str(item_id)] = {
                "selectionId": int(item_id),
                "runnerName": runner_name,
                "price": price,
                "backPrice": back_price,
                "layPrice": lay_price,
                "side": side,
            }

            self._recalculate()
        except Exception:
            pass

    def _show_runner_context_menu(self, event):
        try:
            row_id = self.runners_tree.identify_row(event.y)
            if row_id:
                self.runners_tree.selection_set(row_id)
                self.runners_tree.focus(row_id)
                self.runner_context_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
        finally:
            try:
                self.runner_context_menu.grab_release()
            except Exception:
                pass

    def _book_selected_runner(self):
        try:
            row_id = self.runners_tree.focus()
            if not row_id:
                return
            self._safe_message("info", "Prenotazione", f"Runner {row_id} prenotato.")
        except Exception:
            pass

    # =========================================================
    # DUTCHING PANEL
    # =========================================================

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
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=dutch_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        try:
            canvas.bind_all(
                "<MouseWheel>",
                lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
            )
        except Exception:
            pass

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        type_frame = ctk.CTkFrame(dutch_frame, fg_color="transparent")
        type_frame.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkLabel(type_frame, text="Tipo:", text_color=COLORS["text_secondary"]).pack(side=tk.LEFT)

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
            stake_frame,
            text="Stake Totale (EUR):",
            text_color=COLORS["text_secondary"],
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
            dutch_frame,
            columns=("sel", "tipo", "p/l"),
            show="headings",
            height=4,
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
        self.market_cashout_positions: Dict[str, Dict[str, Any]] = {}

        if not hasattr(self, "selected_runners"):
            self.selected_runners = {}

    def _set_bet_type(self, bet_type: str):
        self.bet_type_var.set(bet_type)
        try:
            if bet_type == "BACK":
                self.back_btn.configure(fg_color=COLORS["back"])
                self.lay_btn.configure(fg_color=COLORS["button_secondary"])
            else:
                self.lay_btn.configure(fg_color=COLORS["lay"])
                self.back_btn.configure(fg_color=COLORS["button_secondary"])
        except Exception:
            pass
        self._recalculate()

    def _clear_selections(self):
        self.selected_runners = {}
        self._recalculate()

    def _recalculate(self):
        try:
            total_stake = self._parse_float(self.stake_var.get(), 0.0)
            selected = list(getattr(self, "selected_runners", {}).values())

            try:
                self.selections_text.configure(state=tk.NORMAL)
                self.selections_text.delete("1.0", tk.END)
            except Exception:
                pass

            if not selected:
                try:
                    self.selections_text.insert("1.0", "Nessuna selezione.")
                    self.selections_text.configure(state=tk.DISABLED)
                except Exception:
                    pass
                try:
                    self.place_btn.configure(state=tk.DISABLED)
                    self.profit_label.configure(text="Profitto: -")
                    self.prob_label.configure(text="Probabilita Implicita: -")
                except Exception:
                    pass
                return

            lines = []
            implied = 0.0
            split_stake = total_stake / len(selected) if selected and total_stake > 0 else 0.0

            for row in selected:
                price = self._parse_float(row.get("price"), 0.0)
                if price > 1.0:
                    implied += 1.0 / price
                lines.append(
                    f"{row.get('runnerName', 'Runner')} | "
                    f"{row.get('side', self.bet_type_var.get())} | "
                    f"@ {price:.2f} | stake ~ {split_stake:.2f}"
                )

            try:
                self.selections_text.insert("1.0", "\n".join(lines))
                self.selections_text.configure(state=tk.DISABLED)
                self.profit_label.configure(
                    text=f"Profitto stimato: {'-' if implied >= 1 else ''}"
                )
                self.prob_label.configure(text=f"Probabilita Implicita: {implied * 100:.2f}%")
                self.place_btn.configure(state=tk.NORMAL if total_stake > 0 else tk.DISABLED)
            except Exception:
                pass
        except Exception:
            try:
                self.place_btn.configure(state=tk.DISABLED)
            except Exception:
                pass

    def _open_dutching_window(self):
        try:
            from dutching_ui import open_dutching_window
        except Exception as e:
            return self._safe_message("error", "Dutching", f"Import dutching_ui fallito:\n{e}")

        market = getattr(self, "current_market", {}) or {}
        event = getattr(self, "current_event", {}) or {}

        market_data = {
            "marketId": market.get("marketId", ""),
            "marketName": market.get("marketName", ""),
            "eventName": event.get("name", ""),
            "startTime": event.get("date", ""),
            "status": market.get("status", "OPEN"),
        }

        runners = market.get("runners", []) or []
        if not runners:
            return self._safe_message("warning", "Dutching", "Nessun runner disponibile.")

        def on_submit(orders):
            self._submit_dutching_orders_from_modal(orders)

        def on_refresh():
            try:
                self._load_runners_for_current_market()
            except Exception:
                pass

        try:
            open_dutching_window(
                parent=self.root,
                market_data=market_data,
                runners=runners,
                on_submit=on_submit,
                on_refresh=on_refresh,
            )
        except Exception as e:
            self._safe_message("error", "Dutching", f"Errore apertura finestra:\n{e}")

    def _submit_dutching_orders_from_modal(self, orders: List[Dict[str, Any]]):
        if not orders:
            return

        market = getattr(self, "current_market", {}) or {}
        event = getattr(self, "current_event", {}) or {}

        results = []
        total_stake = 0.0

        for o in orders:
            stake = self._parse_float(o.get("size"), 0.0)
            total_stake += stake
            results.append(
                {
                    "selectionId": int(o.get("selectionId")),
                    "runnerName": o.get("runnerName", ""),
                    "price": self._parse_float(o.get("price"), 0.0),
                    "stake": stake,
                    "side": o.get("side", self.bet_type_var.get()),
                    "effectiveType": o.get("side", self.bet_type_var.get()),
                }
            )

        payload = {
            "market_id": str(market.get("marketId", "")),
            "market_type": market.get("marketType", "MATCH_ODDS"),
            "event_name": event.get("name", ""),
            "market_name": market.get("marketName", ""),
            "results": results,
            "bet_type": self.bet_type_var.get(),
            "total_stake": total_stake,
            "use_best_price": bool(self.best_price_var.get()),
            "simulation_mode": bool(getattr(self, "simulation_mode", False)),
            "source": "UI_MODAL",
        }

        try:
            self.bus.publish("REQ_PLACE_DUTCHING", payload)
        except Exception as e:
            self._safe_message("error", "Dutching", f"Invio OMS fallito:\n{e}")

    def _place_bets(self):
        selected = list(getattr(self, "selected_runners", {}).values())
        if not selected:
            return self._safe_message("warning", "Piazza Scommesse", "Nessuna selezione.")

        total_stake = self._parse_float(self.stake_var.get(), 0.0)
        if total_stake <= 0:
            return self._safe_message("warning", "Piazza Scommesse", "Stake non valido.")

        split_stake = total_stake / len(selected)
        market = getattr(self, "current_market", {}) or {}
        event = getattr(self, "current_event", {}) or {}

        for row in selected:
            payload = {
                "market_id": str(market.get("marketId", "")),
                "market_type": market.get("marketType", "MATCH_ODDS"),
                "event_name": event.get("name", ""),
                "market_name": market.get("marketName", ""),
                "selection_id": int(row["selectionId"]),
                "runner_name": row.get("runnerName", ""),
                "bet_type": row.get("side", self.bet_type_var.get()),
                "price": self._parse_float(row.get("price"), 0.0),
                "stake": split_stake,
                "simulation_mode": bool(getattr(self, "simulation_mode", False)),
                "source": "UI",
            }
            try:
                self.bus.publish("REQ_QUICK_BET", payload)
            except Exception as e:
                self._safe_message("error", "Piazza Scommesse", f"Errore invio OMS:\n{e}")
                return

    # =========================================================
    # CASHOUT
    # =========================================================

    def _toggle_market_live_tracking(self):
        enabled = bool(self.market_live_tracking_var.get())
        if enabled:
            self._start_market_live_tracking()
        else:
            self._stop_market_live_tracking()

    def _start_market_live_tracking(self):
        self._stop_market_live_tracking()

        try:
            self.market_live_status.configure(text="LIVE ON", text_color=COLORS["success"])
        except Exception:
            pass

        def _tick():
            try:
                self._update_market_cashout_positions()
            except Exception:
                pass

            try:
                if self.market_live_tracking_var.get():
                    self.market_live_tracking_id = self.root.after(3000, _tick)
            except Exception:
                self.market_live_tracking_id = None

        try:
            self.market_live_tracking_id = self.root.after(3000, _tick)
        except Exception:
            self.market_live_tracking_id = None

    def _stop_market_live_tracking(self):
        self._safe_after_cancel("market_live_tracking_id")
        try:
            self.market_live_status.configure(text="LIVE OFF", text_color=COLORS["text_secondary"])
        except Exception:
            pass

    def _update_market_cashout_positions(self):
        self._tree_clear(self.market_cashout_tree)
        self.market_cashout_positions = {}

        if not getattr(self, "current_market", None):
            return

        try:
            if hasattr(self, "client") and self.client and hasattr(self.client, "get_position"):
                positions = self.client.get_position(self.current_market["marketId"])
            else:
                positions = []
        except Exception:
            positions = []

        for pos in positions or []:
            selection_id = str(pos.get("selection_id", pos.get("selectionId", "")))
            runner_name = pos.get("runner_name", pos.get("runnerName", selection_id))
            side = pos.get("side", "")
            pnl = self._parse_float(pos.get("profit_loss", pos.get("pnl", 0.0)), 0.0)

            tag = "profit" if pnl >= 0 else "loss"

            try:
                self.market_cashout_tree.insert(
                    "",
                    tk.END,
                    iid=selection_id if selection_id else None,
                    values=(runner_name, side, f"{pnl:.2f}"),
                    tags=(tag,),
                )
            except Exception:
                pass

            self.market_cashout_positions[selection_id] = pos

        try:
            self.market_cashout_btn.configure(
                state=tk.NORMAL if self.market_cashout_positions else tk.DISABLED
            )
        except Exception:
            pass

    def _do_single_cashout(self, event=None):
        try:
            row_id = self.market_cashout_tree.focus()
            if not row_id:
                return
            position = self.market_cashout_positions.get(str(row_id))
            if not position:
                return
            self._submit_cashout(position)
        except Exception:
            pass

    def _do_market_cashout(self):
        for _, position in list(self.market_cashout_positions.items()):
            self._submit_cashout(position)

    def _submit_cashout(self, position: Dict[str, Any]):
        market = getattr(self, "current_market", {}) or {}

        payload = {
            "market_id": str(market.get("marketId", "")),
            "selection_id": int(position.get("selection_id", position.get("selectionId", 0))),
            "side": position.get("cashout_side", "LAY"),
            "stake": self._parse_float(position.get("cashout_stake", 0.0), 0.0),
            "price": self._parse_float(position.get("cashout_price", 0.0), 0.0),
            "green_up": self._parse_float(position.get("green_up", 0.0), 0.0),
            "source": "UI_CASHOUT",
        }

        try:
            self.bus.publish("REQ_EXECUTE_CASHOUT", payload)
        except Exception as e:
            self._safe_message("error", "Cashout", f"Errore invio cashout:\n{e}")

    # =========================================================
    # ABOUT / UPDATES / SETTINGS
    # =========================================================

    def _show_about(self):
        db_path = "N/D"
        try:
            db_path = getattr(getattr(self, "db", None), "db_path", "N/D")
        except Exception:
            pass

        markets_preview = "\n".join([f"- {v}" for _, v in list(MARKET_TYPES.items())[:8]])

        messagebox.showinfo(
            "Informazioni",
            f"{APP_NAME}\n"
            f"Versione {APP_VERSION}\n\n"
            f"Applicazione per dutching su Betfair Exchange Italia.\n\n"
            f"Mercati supportati:\n"
            f"{markets_preview}\n"
            f"...e altri\n\n"
            f"Database:\n{db_path}\n\n"
            f"Requisiti:\n"
            f"- Account Betfair Italia\n"
            f"- Certificato SSL per API\n"
            f"- App Key Betfair",
        )

    def _check_for_updates_on_startup(self):
        settings = self._safe_get_db_settings()
        update_url = settings.get("update_url") or DEFAULT_UPDATE_URL
        if not update_url:
            return

        skipped_version = settings.get("skipped_version")

        def on_update_result(result):
            try:
                if result.get("update_available") and (
                    not skipped_version
                    or result.get("latest_version", "") != skipped_version
                ):
                    self.root.after(
                        100,
                        lambda: self.uiq.post(self._show_update_notification, result),
                    )
            except Exception:
                pass

        try:
            check_for_updates(APP_VERSION, callback=on_update_result, update_url=update_url)
        except Exception:
            pass

    def _show_update_notification(self, update_info):
        try:
            choice = show_update_dialog(self.root, update_info)
            if choice == "skip" and hasattr(self, "db") and self.db:
                self.db.save_skipped_version(update_info.get("latest_version"))
        except Exception:
            pass

    def _check_for_updates_manual(self):
        settings = self._safe_get_db_settings()
        update_url = settings.get("update_url") or DEFAULT_UPDATE_URL
        if not update_url:
            return self._safe_message(
                "info",
                "Aggiornamenti",
                "Nessun URL di aggiornamento configurato.\n\nVai su File > Configura Aggiornamenti per impostarlo.",
            )

        def on_result(result):
            try:
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
            except Exception:
                pass

        try:
            check_for_updates(APP_VERSION, callback=on_result, update_url=update_url)
        except Exception as e:
            self._safe_message("error", "Aggiornamenti", f"Errore verifica:\n{e}")

    def _show_update_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Aggiornamenti")
        dialog.geometry("500x250")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Configura Aggiornamenti Automatici",
            style="Title.TLabel",
        ).pack(pady=(0, 15))

        settings = self._safe_get_db_settings()

        ttk.Label(frame, text="URL GitHub Releases API:").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text=f"(Default: {DEFAULT_UPDATE_URL})",
            foreground="gray",
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W)

        url_var = tk.StringVar(value=settings.get("update_url", "") or DEFAULT_UPDATE_URL)
        ttk.Entry(frame, textvariable=url_var, width=60).pack(fill=tk.X, pady=(5, 15))

        ttk.Label(
            frame,
            text="L'app controllera' automaticamente gli aggiornamenti all'avvio.",
            foreground="gray",
        ).pack(anchor=tk.W)

        def save():
            try:
                if hasattr(self, "db") and self.db:
                    self.db.save_update_url(url_var.get().strip())
                    self.db.save_skipped_version(None)
            except Exception:
                pass
            dialog.destroy()
            self._safe_message("info", "Salvato", "Impostazioni aggiornamento salvate!")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=15)
        ttk.Button(btn_frame, text="Salva", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annulla", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame,
            text="Verifica Ora",
            command=lambda: [dialog.destroy(), self._check_for_updates_manual()],
        ).pack(side=tk.RIGHT, padx=5)

    def _load_settings(self):
        settings = self._safe_get_db_settings()
        if settings and settings.get("session_token"):
            self._try_restore_session(settings)

    def _try_restore_session(self, settings: Dict[str, Any]):
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
            except Exception:
                pass

    def _show_credentials_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Configura Credenziali Betfair")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        settings = self._safe_get_db_settings()

        ttk.Label(frame, text="Username Betfair:").pack(anchor=tk.W)
        username_var = tk.StringVar(value=settings.get("username", ""))
        ttk.Entry(frame, textvariable=username_var, width=50).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(frame, text="App Key:").pack(anchor=tk.W)
        appkey_var = tk.StringVar(value=settings.get("app_key", ""))
        ttk.Entry(frame, textvariable=appkey_var, width=50).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(frame, text="Certificato SSL (.pem):").pack(anchor=tk.W)
        cert_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        cert_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get("certificate"):
            cert_text.insert("1.0", settings["certificate"])

        def load_file_into(widget):
            filename = filedialog.askopenfilename()
            if not filename:
                return
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", f.read())
            except Exception as e:
                self._safe_message("error", "File", f"Errore lettura file:\n{e}")

        ttk.Button(
            frame,
            text="Carica da file...",
            command=lambda: load_file_into(cert_text),
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Chiave Privata (.key o .pem):").pack(anchor=tk.W)
        key_text = scrolledtext.ScrolledText(frame, height=6, width=50)
        key_text.pack(fill=tk.X, pady=(0, 5))
        if settings.get("private_key"):
            key_text.insert("1.0", settings["private_key"])

        ttk.Button(
            frame,
            text="Carica da file...",
            command=lambda: load_file_into(key_text),
        ).pack(anchor=tk.W, pady=(0, 20))

        def save():
            try:
                if hasattr(self, "db") and self.db and hasattr(self.db, "save_credentials"):
                    self.db.save_credentials(
                        username_var.get(),
                        appkey_var.get(),
                        cert_text.get("1.0", tk.END).strip(),
                        key_text.get("1.0", tk.END).strip(),
                    )
                else:
                    if hasattr(self, "db") and self.db and hasattr(self.db, "save_settings"):
                        self.db.save_settings(
                            {
                                "username": username_var.get(),
                                "app_key": appkey_var.get(),
                                "certificate": cert_text.get("1.0", tk.END).strip(),
                                "private_key": key_text.get("1.0", tk.END).strip(),
                            }
                        )
                self._safe_message("info", "Salvato", "Credenziali salvate")
                dialog.destroy()
            except Exception as e:
                self._safe_message("error", "Errore", f"Salvataggio fallito:\n{e}")

        ttk.Button(frame, text="Salva", command=save).pack(pady=10)

    def _browse_file(self, var, filetypes):
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)

    # =========================================================
    # DASHBOARD
    # =========================================================

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

    def _refresh_dashboard_tab(self):
        for frame in [
            getattr(self, "dashboard_recent_frame", None),
            getattr(self, "dashboard_orders_frame", None),
            getattr(self, "dashboard_bookings_frame", None),
            getattr(self, "dashboard_cashout_frame", None),
        ]:
            if frame:
                for child in frame.winfo_children():
                    try:
                        child.destroy()
                    except Exception:
                        pass

        client = getattr(self, "client", None)
        if not client:
            try:
                self.dashboard_not_connected.pack(pady=20)
            except Exception:
                pass
            return

        try:
            self.dashboard_not_connected.pack_forget()
        except Exception:
            pass

        try:
            if hasattr(self.db, "get_bet_history"):
                history = self.db.get_bet_history(limit=50)
            elif hasattr(self.db, "get_recent_bets"):
                history = self.db.get_recent_bets(limit=50)
            else:
                history = []
        except Exception:
            history = []

        self._create_simple_table(
            self.dashboard_recent_frame,
            columns=("data", "evento", "mercato", "tipo", "stake", "stato"),
            rows=[
                (
                    str(b.get("placed_at", ""))[:16],
                    b.get("event_name", ""),
                    b.get("market_name", ""),
                    b.get("bet_type", ""),
                    f"{self._parse_float(b.get('total_stake', 0.0), 0.0):.2f}",
                    b.get("status", ""),
                )
                for b in history or []
            ],
        )

        try:
            orders = client.get_current_orders() if hasattr(client, "get_current_orders") else {}
        except Exception:
            orders = {}

        current_rows = []
        for o in (orders.get("currentOrders", []) or orders.get("matched", []) or []):
            current_rows.append(
                (
                    o.get("marketId", ""),
                    o.get("selectionId", ""),
                    o.get("side", ""),
                    o.get("price", o.get("priceSize", {}).get("price", "")),
                    o.get("sizeMatched", o.get("size", "")),
                    o.get("status", ""),
                )
            )

        self._create_simple_table(
            self.dashboard_orders_frame,
            columns=("market", "selection", "tipo", "quota", "size", "stato"),
            rows=current_rows,
        )

        self._create_simple_table(
            self.dashboard_bookings_frame,
            columns=("info",),
            rows=[("Nessuna prenotazione avanzata disponibile",)],
        )

        try:
            cashouts = self.db.get_cashout_history(limit=50) if hasattr(self.db, "get_cashout_history") else []
        except Exception:
            cashouts = []

        self._create_simple_table(
            self.dashboard_cashout_frame,
            columns=("market", "selection", "stake", "price", "pnl"),
            rows=[
                (
                    c.get("market_id", ""),
                    c.get("selection_id", ""),
                    c.get("cashout_stake", ""),
                    c.get("cashout_price", ""),
                    c.get("profit_loss", ""),
                )
                for c in cashouts or []
            ],
        )

    def _create_simple_table(self, parent, columns, rows):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tree = ttk.Treeview(container, columns=columns, show="headings", height=12)
        for col in columns:
            tree.heading(col, text=col.capitalize())
            tree.column(col, width=120)

        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for row in rows or []:
            try:
                tree.insert("", tk.END, values=row)
            except Exception:
                pass

    # =========================================================
    # STRUMENTI / PLUGIN / IMPOSTAZIONI / SIMULAZIONE
    # =========================================================

    def _create_strumenti_tab(self):
        frame = ctk.CTkFrame(self.strumenti_tab, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Strumenti",
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 20))

        ctk.CTkButton(
            frame,
            text="Multi-Market Monitor",
            command=self._show_multi_market_monitor,
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["back_hover"],
        ).pack(anchor=tk.W, pady=5)

        ctk.CTkButton(
            frame,
            text="Reset Simulazione",
            command=self._reset_simulation,
            fg_color=COLORS["button_danger"],
            hover_color="#c62828",
        ).pack(anchor=tk.W, pady=5)

    def _create_plugin_tab(self):
        frame = ctk.CTkFrame(self.plugin_tab, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Plugin",
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 20))

        self.plugin_status_label = ctk.CTkLabel(
            frame,
            text="Plugin manager pronto",
            text_color=COLORS["text_secondary"],
        )
        self.plugin_status_label.pack(anchor=tk.W)

    def _create_impostazioni_tab(self):
        frame = ctk.CTkFrame(self.impostazioni_tab, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Impostazioni",
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 20))

        ctk.CTkButton(
            frame,
            text="Credenziali Betfair",
            command=self._show_credentials_dialog,
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["back_hover"],
        ).pack(anchor=tk.W, pady=5)

        ctk.CTkButton(
            frame,
            text="Aggiornamenti",
            command=self._show_update_settings_dialog,
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["bg_hover"],
        ).pack(anchor=tk.W, pady=5)

    def _create_simulazione_tab(self):
        frame = ctk.CTkFrame(self.simulazione_tab, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Simulazione",
            font=FONTS["title"],
            text_color=COLORS["text_primary"],
        ).pack(anchor=tk.W, pady=(0, 20))

        self.sim_info_label = ctk.CTkLabel(
            frame,
            text="Modalità simulazione non attiva",
            text_color=COLORS["text_secondary"],
        )
        self.sim_info_label.pack(anchor=tk.W, pady=(0, 10))

        list_frame = ctk.CTkFrame(frame, fg_color="transparent")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self._create_simulation_bets_list(list_frame)
        self._refresh_simulation_balance_ui()

    def _create_simulation_bets_list(self, parent):
        try:
            sim_bets = self.db.get_simulation_bets(limit=50) if hasattr(self.db, "get_simulation_bets") else []
        except Exception:
            sim_bets = []

        try:
            sim_settings = self.db.get_simulation_settings() if hasattr(self.db, "get_simulation_settings") else {}
        except Exception:
            sim_settings = {}

        if sim_settings:
            balance = self._parse_float(sim_settings.get("virtual_balance", 1000), 1000.0)
            starting = self._parse_float(sim_settings.get("starting_balance", 1000), 1000.0)
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
                text=f"  |  P/L: {('+' + str(round(pl, 2))) if pl >= 0 else round(pl, 2)} EUR",
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
            ttk.Label(parent, text="Nessuna scommessa simulata", font=("Segoe UI", 10)).pack(pady=20)

        for bet in sim_bets:
            tree.insert(
                "",
                tk.END,
                values=(
                    bet.get("placed_at", "")[:16] if bet.get("placed_at") else "",
                    bet.get("event_name", "")[:25],
                    bet.get("market_name", "")[:20],
                    bet.get("side", ""),
                    f"{self._parse_float(bet.get('total_stake', 0), 0):.2f}",
                    (
                        f"+{self._parse_float(bet.get('potential_profit', 0), 0):.2f}"
                        if self._parse_float(bet.get("potential_profit", 0), 0) > 0
                        else f"{self._parse_float(bet.get('potential_profit', 0), 0):.2f}"
                    ),
                ),
            )

    def _reset_simulation(self):
        try:
            if hasattr(self.db, "save_settings"):
                self.db.save_settings({"virtual_balance": 1000.0})
            if hasattr(self.db, "reset_simulation"):
                self.db.reset_simulation()
            self._safe_message("info", "Simulazione", "Simulazione resettata.")
        except Exception as e:
            self._safe_message("error", "Simulazione", f"Reset fallito:\n{e}")

    def _refresh_simulation_balance_ui(self):
        try:
            settings = self.db.get_simulation_settings() if hasattr(self.db, "get_simulation_settings") else {}
        except Exception:
            settings = {}

        balance = self._parse_float(settings.get("virtual_balance", 0.0), 0.0)
        try:
            self.sim_balance_label.configure(text=f"SIM: {balance:.2f} EUR")
        except Exception:
            pass
        try:
            self.sim_info_label.configure(
                text=f"Saldo virtuale: {balance:.2f} EUR"
                if getattr(self, "simulation_mode", False)
                else "Modalità simulazione non attiva"
            )
        except Exception:
            pass

    # =========================================================
    # LIVE / SIM / DATA
    # =========================================================

    def _refresh_data(self):
        try:
            if hasattr(self, "_update_balance"):
                self._update_balance()
        except Exception:
            pass

        try:
            if hasattr(self, "_load_events"):
                self._load_events()
        except Exception:
            pass

        try:
            if getattr(self, "current_market", None):
                self._load_runners_for_current_market()
        except Exception:
            pass

        try:
            self._update_market_cashout_positions()
        except Exception:
            pass

        try:
            self._refresh_dashboard_tab()
        except Exception:
            pass

        try:
            self._refresh_simulation_balance_ui()
        except Exception:
            pass

    def _toggle_live_mode(self):
        current = bool(getattr(self, "live_mode", False))
        self.live_mode = not current

        try:
            self.live_btn.configure(
                fg_color=COLORS["success"] if self.live_mode else COLORS["loss"],
                text="LIVE ON" if self.live_mode else "LIVE",
            )
        except Exception:
            pass

    def _toggle_simulation_mode(self):
        current = bool(getattr(self, "simulation_mode", False))
        self.simulation_mode = not current

        try:
            self.sim_btn.configure(
                fg_color=COLORS["warning"] if self.simulation_mode else COLORS["button_secondary"],
                text="SIM ON" if self.simulation_mode else "SIMULAZIONE",
            )
        except Exception:
            pass

        self._refresh_simulation_balance_ui()

    # =========================================================
    # MULTI MARKET MONITOR
    # =========================================================

    def _show_multi_market_monitor(self):
        if not getattr(self, "client", None):
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

        ttk.Label(control_frame, text="Aggiungi mercato corrente alla watchlist:").pack(side=tk.LEFT)

        def add_current_market():
            if getattr(self, "current_market", None) and getattr(self, "current_event", None):
                market_info = {
                    "event_id": self.current_event["id"],
                    "event_name": self.current_event["name"],
                    "market_id": self.current_market["marketId"],
                    "market_name": self.current_market.get("marketName", "N/A"),
                    "runners": self.current_market.get("runners", []),
                }
                for m in self.watchlist:
                    if m["market_id"] == market_info["market_id"]:
                        return messagebox.showinfo("Info", "Mercato già nella watchlist")
                self.watchlist.append(market_info)
                refresh_watchlist()
                messagebox.showinfo("Aggiunto", f"Aggiunto: {market_info['event_name']}")
            else:
                messagebox.showwarning("Attenzione", "Seleziona prima un mercato")

        ttk.Button(control_frame, text="+ Aggiungi Corrente", command=add_current_market).pack(side=tk.LEFT, padx=10)

        monitor_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            control_frame,
            text="Auto-refresh (30s)",
            variable=monitor_refresh_var,
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(
            control_frame,
            text="Aggiorna Ora",
            command=lambda: refresh_watchlist(),
        ).pack(side=tk.LEFT, padx=5)

        watch_container = ttk.Frame(main_frame)
        watch_container.pack(fill=tk.BOTH, expand=True)

        watch_tree = ttk.Treeview(
            watch_container,
            columns=("evento", "mercato", "runners"),
            show="headings",
            height=20,
        )
        watch_tree.heading("evento", text="Evento")
        watch_tree.heading("mercato", text="Mercato")
        watch_tree.heading("runners", text="Runner")
        watch_tree.column("evento", width=250)
        watch_tree.column("mercato", width=250)
        watch_tree.column("runners", width=350)

        scroll = ttk.Scrollbar(watch_container, orient=tk.VERTICAL, command=watch_tree.yview)
        watch_tree.configure(yscrollcommand=scroll.set)
        watch_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btns = ttk.Frame(main_frame)
        btns.pack(fill=tk.X, pady=(10, 0))

        def remove_selected():
            selected = watch_tree.selection()
            if not selected:
                return
            ids = set(selected)
            self.watchlist = [w for w in self.watchlist if str(w.get("market_id")) not in ids]
            refresh_watchlist()

        ttk.Button(btns, text="Rimuovi Selezionato", command=remove_selected).pack(side=tk.LEFT)

        def refresh_watchlist():
            try:
                watch_tree.delete(*watch_tree.get_children())
            except Exception:
                pass

            for item in self.watchlist:
                runners = item.get("runners", []) or []
                runner_names = ", ".join(r.get("runnerName", "") for r in runners[:4])
                if len(runners) > 4:
                    runner_names += " ..."
                try:
                    watch_tree.insert(
                        "",
                        tk.END,
                        iid=str(item.get("market_id")),
                        values=(
                            item.get("event_name", ""),
                            item.get("market_name", ""),
                            runner_names,
                        ),
                    )
                except Exception:
                    pass

        def auto_refresh_tick():
            if not monitor.winfo_exists():
                return
            try:
                refresh_watchlist()
            except Exception:
                pass
            if monitor_refresh_var.get():
                monitor.after(30000, auto_refresh_tick)

        refresh_watchlist()
        if monitor_refresh_var.get():
            monitor.after(30000, auto_refresh_tick)
