"""
Dutching Confirmation Window - UI stile Bet Angel
Finestra separata per conferma e gestione dutching avanzato.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from typing import Callable, Optional, Dict, List

from theme import COLORS, FONTS
from dutching_state import DutchingState, DutchingMode, RunnerState
from dutching import (
    calculate_dutching_stakes, 
    calculate_mixed_dutching,
    calculate_ai_mixed_stakes,
    validate_selections,
    format_currency,
    MIN_BACK_STAKE
)
from trading_config import BOOK_WARNING, BOOK_BLOCK, MIN_STAKE
from market_validator import MarketValidator


class DutchingConfirmationWindow:
    """
    Finestra Dutching Confirmation con:
    - Header mercato
    - Selezione modalità (Stake Available / Required Profit)
    - Tabella runner reattiva
    - Footer con controlli globali
    """
    
    def __init__(self, parent, state: DutchingState, 
                 on_submit: Callable[[List[Dict]], None],
                 on_refresh_odds: Optional[Callable] = None):
        """
        Args:
            parent: Finestra padre
            state: DutchingState con dati mercato/runner
            on_submit: Callback per submit ordini
            on_refresh_odds: Callback per aggiornare quote live
        """
        self.parent = parent
        self.state = state
        self.on_submit = on_submit
        self.on_refresh_odds = on_refresh_odds
        
        # Crea finestra
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Dutching Confirmation")
        self.window.configure(fg_color=COLORS['bg_dark'])
        
        # Dimensioni e posizione
        width, height = 800, 600
        x = parent.winfo_x() + (parent.winfo_width() - width) // 2
        y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(700, 500)
        
        # Modal
        self.window.transient(parent)
        self.window.grab_set()
        
        # Variabili UI
        self._mode_var = tk.StringVar(value="stake")
        self._stake_var = tk.StringVar(value=str(self.state.total_stake))
        self._profit_var = tk.StringVar(value=str(self.state.target_profit))
        self._auto_ratio_var = tk.BooleanVar(value=self.state.auto_ratio)
        self._live_odds_var = tk.BooleanVar(value=self.state.live_odds)
        self._global_offset_var = tk.StringVar(value="0")
        self._swap_all_var = tk.BooleanVar(value=False)
        self._mixed_mode_var = tk.BooleanVar(value=False)
        
        # PRO Features
        self._ai_mode_var = tk.BooleanVar(value=False)
        self._auto_green_var = tk.BooleanVar(value=False)
        self._simulation_var = tk.BooleanVar(value=getattr(self.state, 'simulation_mode', False))
        
        # Mappa checkbox per runner (modalità normale)
        self._runner_checkboxes: Dict[int, tk.BooleanVar] = {}
        self._runner_swap_vars: Dict[int, tk.BooleanVar] = {}
        self._runner_offset_vars: Dict[int, tk.StringVar] = {}
        self._runner_odds_vars: Dict[int, tk.StringVar] = {}
        
        # Mappa checkbox per modalità Mixed (BACK e LAY separati)
        self._runner_back_vars: Dict[int, tk.BooleanVar] = {}
        self._runner_lay_vars: Dict[int, tk.BooleanVar] = {}
        self._runner_back_stake_vars: Dict[int, tk.StringVar] = {}
        self._runner_lay_stake_vars: Dict[int, tk.StringVar] = {}
        
        # Mappa widget righe per aggiornamento
        self._runner_widgets: Dict[int, Dict] = {}
        
        # Costruisci UI
        self._build_ui()
        
        # Connetti callback stato
        self.state.set_callback(self._on_state_change)
        
        # Calcolo iniziale
        self._recalculate()
    
    def _build_ui(self):
        """Costruisce interfaccia completa."""
        main_frame = ctk.CTkFrame(self.window, fg_color=COLORS['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 1. HEADER - Info mercato
        self._build_header(main_frame)
        
        # 2. DUTCHING TYPE - Selezione modalità
        self._build_mode_section(main_frame)
        
        # 3. TABELLA RUNNER
        self._build_runner_table(main_frame)
        
        # 4. FOOTER - Controlli globali
        self._build_footer(main_frame)
    
    def _build_header(self, parent):
        """Header con info mercato."""
        header_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_panel'], corner_radius=8)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Market info
        market_label = ctk.CTkLabel(
            header_frame, 
            text=self.state.market_display,
            font=FONTS['heading'],
            text_color=COLORS['text_primary']
        )
        market_label.pack(side=tk.LEFT, padx=15, pady=10)
        
        # Status badge
        status = self.state.market_status
        status_color = COLORS['profit'] if status == "OPEN" else COLORS['warning']
        status_text = "LIVE" if status == "OPEN" else status
        
        self.status_badge = ctk.CTkLabel(
            header_frame,
            text=status_text,
            font=FONTS['small'],
            text_color=COLORS['bg_dark'],
            fg_color=status_color,
            corner_radius=4,
            width=80
        )
        self.status_badge.pack(side=tk.RIGHT, padx=15, pady=10)
        
        # Simulation Mode banner (nascosto di default)
        self._sim_banner = ctk.CTkLabel(
            header_frame,
            text="SIMULATION MODE",
            font=FONTS['heading'],
            text_color="#FF4444",
            fg_color="transparent"
        )
        # Non visualizzato di default - pack_forget chiamato in _update_simulation_banner
    
    def _build_mode_section(self, parent):
        """Sezione Dutching Type."""
        mode_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_surface'], corner_radius=8)
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Titolo
        title = ctk.CTkLabel(mode_frame, text="Dutching Type", 
                            font=FONTS['heading'], text_color=COLORS['text_primary'])
        title.grid(row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(10, 5))
        
        # Radio: Stake Available
        stake_radio = ctk.CTkRadioButton(
            mode_frame, text="Stake Available",
            variable=self._mode_var, value="stake",
            command=self._on_mode_change,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['back'],
            hover_color=COLORS['back_hover']
        )
        stake_radio.grid(row=1, column=0, padx=15, pady=5, sticky="w")
        
        # Input stake
        self.stake_entry = ctk.CTkEntry(
            mode_frame, textvariable=self._stake_var,
            width=100, font=FONTS['default'],
            fg_color=COLORS['bg_panel'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border']
        )
        self.stake_entry.grid(row=1, column=1, padx=5, pady=5)
        self.stake_entry.bind('<Return>', lambda e: self._recalculate())
        self.stake_entry.bind('<FocusOut>', lambda e: self._recalculate())
        
        # Radio: Required Profit
        profit_radio = ctk.CTkRadioButton(
            mode_frame, text="Required Profit",
            variable=self._mode_var, value="profit",
            command=self._on_mode_change,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['back'],
            hover_color=COLORS['back_hover']
        )
        profit_radio.grid(row=2, column=0, padx=15, pady=5, sticky="w")
        
        # Input profit
        self.profit_entry = ctk.CTkEntry(
            mode_frame, textvariable=self._profit_var,
            width=100, font=FONTS['default'],
            fg_color=COLORS['bg_panel'],
            text_color=COLORS['text_primary'],
            border_color=COLORS['border']
        )
        self.profit_entry.grid(row=2, column=1, padx=5, pady=5)
        self.profit_entry.bind('<Return>', lambda e: self._recalculate())
        self.profit_entry.bind('<FocusOut>', lambda e: self._recalculate())
        
        # Checkbox: Automatic Ratio
        auto_check = ctk.CTkCheckBox(
            mode_frame, text="Automatic Ratio",
            variable=self._auto_ratio_var,
            command=self._on_auto_ratio_change,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['back'],
            hover_color=COLORS['back_hover']
        )
        auto_check.grid(row=1, column=2, padx=30, pady=5)
        
        # Pulsante Mixed Mode
        self.mixed_btn = ctk.CTkButton(
            mode_frame, text="Mixed Mode",
            command=self._toggle_mixed_mode,
            fg_color=COLORS['button_secondary'],
            hover_color=COLORS['bg_hover'],
            width=120
        )
        self.mixed_btn.grid(row=2, column=2, padx=30, pady=5)
        
        # Pulsante AI Mode (PRO)
        self.ai_btn = ctk.CTkButton(
            mode_frame, text="AI Auto",
            command=self._toggle_ai_mode,
            fg_color=COLORS['button_secondary'],
            hover_color=COLORS['bg_hover'],
            width=80
        )
        self.ai_btn.grid(row=1, column=3, padx=5, pady=5)
        
        # Book Value
        self.book_label = ctk.CTkLabel(
            mode_frame, text="Book: 0%",
            font=FONTS['mono'],
            text_color=COLORS['text_secondary']
        )
        self.book_label.grid(row=2, column=3, padx=5, pady=5)
        
        mode_frame.grid_columnconfigure(4, weight=1)
    
    def _build_runner_table(self, parent):
        """Tabella runner principale."""
        table_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_surface'], corner_radius=8)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Header tabella
        headers = ["", "Selection", "Offset", "Swap", "Odds", "Stake", "Profit/Loss"]
        widths = [40, 200, 80, 60, 100, 100, 120]
        
        header_frame = ctk.CTkFrame(table_frame, fg_color=COLORS['bg_panel'], corner_radius=0)
        header_frame.pack(fill=tk.X)
        
        for i, (header, width) in enumerate(zip(headers, widths)):
            lbl = ctk.CTkLabel(
                header_frame, text=header,
                font=('Segoe UI', 10, 'bold'),
                text_color=COLORS['text_primary'],
                width=width
            )
            lbl.grid(row=0, column=i, padx=2, pady=8, sticky="w" if i < 2 else "")
        
        # Scrollable frame per runner
        self.runners_scroll = ctk.CTkScrollableFrame(
            table_frame, fg_color=COLORS['bg_surface'],
            scrollbar_button_color=COLORS['bg_panel'],
            scrollbar_button_hover_color=COLORS['bg_hover']
        )
        self.runners_scroll.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Popola righe
        self._populate_runner_rows()
    
    def _populate_runner_rows(self):
        """Crea righe per ogni runner."""
        # Pulisci righe esistenti
        for widget in self.runners_scroll.winfo_children():
            widget.destroy()
        
        self._runner_checkboxes.clear()
        self._runner_swap_vars.clear()
        self._runner_offset_vars.clear()
        self._runner_odds_vars.clear()
        self._runner_back_vars.clear()
        self._runner_lay_vars.clear()
        self._runner_widgets.clear()
        
        if self._mixed_mode_var.get():
            # Modalità Mixed: due righe per runner (BACK + LAY)
            for idx, runner in enumerate(self.state.runners):
                self._create_mixed_runner_rows(idx, runner)
        else:
            # Modalità normale: una riga per runner
            for idx, runner in enumerate(self.state.runners):
                self._create_runner_row(idx, runner)
    
    def _create_runner_row(self, idx: int, runner: RunnerState):
        """Crea singola riga runner."""
        row_frame = ctk.CTkFrame(
            self.runners_scroll,
            fg_color=COLORS['bg_panel'] if idx % 2 == 0 else COLORS['bg_surface'],
            corner_radius=4
        )
        row_frame.pack(fill=tk.X, pady=1)
        
        sel_id = runner.selection_id
        
        # Checkbox inclusione
        include_var = tk.BooleanVar(value=runner.included)
        self._runner_checkboxes[sel_id] = include_var
        
        check = ctk.CTkCheckBox(
            row_frame, text="",
            variable=include_var,
            command=lambda s=sel_id: self._toggle_runner(s),
            width=40,
            fg_color=COLORS['back'],
            hover_color=COLORS['back_hover']
        )
        check.grid(row=0, column=0, padx=5, pady=8)
        
        # Nome selezione
        name_label = ctk.CTkLabel(
            row_frame, text=runner.runner_name,
            font=FONTS['default'],
            text_color=COLORS['text_primary'] if runner.included else COLORS['text_tertiary'],
            width=200, anchor="w"
        )
        name_label.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        
        # Offset spinbox
        offset_var = tk.StringVar(value=str(runner.offset))
        self._runner_offset_vars[sel_id] = offset_var
        
        offset_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        offset_frame.grid(row=0, column=2, padx=5, pady=8)
        
        offset_down = ctk.CTkButton(
            offset_frame, text="-", width=25,
            command=lambda s=sel_id: self._adjust_offset(s, -1),
            fg_color=COLORS['button_secondary']
        )
        offset_down.pack(side=tk.LEFT)
        
        offset_entry = ctk.CTkEntry(
            offset_frame, textvariable=offset_var,
            width=40, font=FONTS['small'],
            fg_color=COLORS['bg_surface'],
            text_color=COLORS['text_primary'],
            justify="center"
        )
        offset_entry.pack(side=tk.LEFT, padx=2)
        
        offset_up = ctk.CTkButton(
            offset_frame, text="+", width=25,
            command=lambda s=sel_id: self._adjust_offset(s, 1),
            fg_color=COLORS['button_secondary']
        )
        offset_up.pack(side=tk.LEFT)
        
        # Swap checkbox (BACK/LAY)
        swap_var = tk.BooleanVar(value=runner.swap)
        self._runner_swap_vars[sel_id] = swap_var
        
        swap_check = ctk.CTkCheckBox(
            row_frame, text="",
            variable=swap_var,
            command=lambda s=sel_id: self._toggle_swap(s),
            width=60,
            fg_color=COLORS['lay'],
            hover_color=COLORS['lay_hover']
        )
        swap_check.grid(row=0, column=3, padx=5, pady=8)
        
        # Odds entry
        odds_var = tk.StringVar(value=f"{runner.effective_odds:.2f}")
        self._runner_odds_vars[sel_id] = odds_var
        
        odds_entry = ctk.CTkEntry(
            row_frame, textvariable=odds_var,
            width=80, font=FONTS['mono'],
            fg_color=COLORS['bg_surface'],
            text_color=COLORS['back'] if not runner.swap else COLORS['lay'],
            justify="center"
        )
        odds_entry.grid(row=0, column=4, padx=5, pady=8)
        odds_entry.bind('<Return>', lambda e, s=sel_id: self._on_odds_change(s))
        odds_entry.bind('<FocusOut>', lambda e, s=sel_id: self._on_odds_change(s))
        
        # Stake label
        stake_text = f"€{runner.stake:.2f}" if runner.included else "€0"
        stake_label = ctk.CTkLabel(
            row_frame, text=stake_text,
            font=FONTS['mono'],
            text_color=COLORS['text_primary'],
            width=100
        )
        stake_label.grid(row=0, column=5, padx=5, pady=8)
        
        # Profit/Loss label
        profit = runner.profit_if_wins
        if runner.included:
            profit_color = COLORS['profit'] if profit >= 0 else COLORS['loss']
            profit_text = f"€{profit:.2f}"
        else:
            profit_color = COLORS['loss']
            profit_text = f"-€{self.state.get_total_stake():.2f}"
        
        profit_label = ctk.CTkLabel(
            row_frame, text=profit_text,
            font=('Segoe UI', 11, 'bold'),
            text_color=profit_color,
            width=120
        )
        profit_label.grid(row=0, column=6, padx=5, pady=8)
        
        # Salva riferimenti per update
        self._runner_widgets[sel_id] = {
            'stake_label': stake_label,
            'profit_label': profit_label,
            'name_label': name_label,
            'odds_entry': odds_entry,
        }
    
    def _create_mixed_runner_rows(self, idx: int, runner: RunnerState):
        """Crea due righe per runner: BACK (blu) e LAY (rosa)."""
        sel_id = runner.selection_id
        
        # Contenitore per le due righe
        container = ctk.CTkFrame(self.runners_scroll, fg_color="transparent")
        container.pack(fill=tk.X, pady=2)
        
        # === RIGA BACK (blu) ===
        back_frame = ctk.CTkFrame(
            container,
            fg_color=COLORS['back'],
            corner_radius=4
        )
        back_frame.pack(fill=tk.X, pady=1)
        
        # Checkbox BACK
        back_var = tk.BooleanVar(value=True)
        self._runner_back_vars[sel_id] = back_var
        
        back_check = ctk.CTkCheckBox(
            back_frame, text="",
            variable=back_var,
            command=lambda s=sel_id: self._toggle_back(s),
            width=40,
            fg_color=COLORS['text_primary'],
            checkmark_color=COLORS['back']
        )
        back_check.grid(row=0, column=0, padx=5, pady=6)
        
        # Nome + "BACK"
        back_name = ctk.CTkLabel(
            back_frame, text=f"{runner.runner_name} - BACK",
            font=FONTS['default'],
            text_color=COLORS['bg_dark'],
            width=220, anchor="w"
        )
        back_name.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        
        # Odds BACK
        back_odds = ctk.CTkLabel(
            back_frame, text=f"{runner.odds:.2f}",
            font=FONTS['mono'],
            text_color=COLORS['bg_dark'],
            width=80
        )
        back_odds.grid(row=0, column=2, padx=5, pady=6)
        
        # Stake BACK
        back_stake_var = tk.StringVar(value="0.00")
        self._runner_back_stake_vars[sel_id] = back_stake_var
        
        back_stake = ctk.CTkLabel(
            back_frame, textvariable=back_stake_var,
            font=FONTS['mono'],
            text_color=COLORS['bg_dark'],
            width=100
        )
        back_stake.grid(row=0, column=3, padx=5, pady=6)
        
        # P&L BACK
        back_pnl = ctk.CTkLabel(
            back_frame, text="€0.00",
            font=('Segoe UI', 10, 'bold'),
            text_color=COLORS['bg_dark'],
            width=100
        )
        back_pnl.grid(row=0, column=4, padx=5, pady=6)
        
        # === RIGA LAY (rosa) ===
        lay_frame = ctk.CTkFrame(
            container,
            fg_color=COLORS['lay'],
            corner_radius=4
        )
        lay_frame.pack(fill=tk.X, pady=1)
        
        # Checkbox LAY
        lay_var = tk.BooleanVar(value=False)
        self._runner_lay_vars[sel_id] = lay_var
        
        lay_check = ctk.CTkCheckBox(
            lay_frame, text="",
            variable=lay_var,
            command=lambda s=sel_id: self._toggle_lay(s),
            width=40,
            fg_color=COLORS['text_primary'],
            checkmark_color=COLORS['lay']
        )
        lay_check.grid(row=0, column=0, padx=5, pady=6)
        
        # Nome + "LAY"
        lay_name = ctk.CTkLabel(
            lay_frame, text=f"{runner.runner_name} - LAY",
            font=FONTS['default'],
            text_color=COLORS['bg_dark'],
            width=220, anchor="w"
        )
        lay_name.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        
        # Odds LAY
        lay_odds = ctk.CTkLabel(
            lay_frame, text=f"{runner.odds:.2f}",
            font=FONTS['mono'],
            text_color=COLORS['bg_dark'],
            width=80
        )
        lay_odds.grid(row=0, column=2, padx=5, pady=6)
        
        # Stake LAY
        lay_stake_var = tk.StringVar(value="0.00")
        self._runner_lay_stake_vars[sel_id] = lay_stake_var
        
        lay_stake = ctk.CTkLabel(
            lay_frame, textvariable=lay_stake_var,
            font=FONTS['mono'],
            text_color=COLORS['bg_dark'],
            width=100
        )
        lay_stake.grid(row=0, column=3, padx=5, pady=6)
        
        # P&L LAY
        lay_pnl = ctk.CTkLabel(
            lay_frame, text="€0.00",
            font=('Segoe UI', 10, 'bold'),
            text_color=COLORS['bg_dark'],
            width=100
        )
        lay_pnl.grid(row=0, column=4, padx=5, pady=6)
        
        # Salva widget per update
        self._runner_widgets[sel_id] = {
            'back_frame': back_frame,
            'lay_frame': lay_frame,
            'back_stake': back_stake,
            'lay_stake': lay_stake,
            'back_pnl': back_pnl,
            'lay_pnl': lay_pnl,
        }
    
    def _toggle_mixed_mode(self):
        """Toggle modalità Mixed BACK/LAY."""
        self._mixed_mode_var.set(not self._mixed_mode_var.get())
        
        # Aggiorna aspetto pulsante
        if self._mixed_mode_var.get():
            self.mixed_btn.configure(
                fg_color=COLORS['warning'],
                text="Mixed: ON"
            )
        else:
            self.mixed_btn.configure(
                fg_color=COLORS['button_secondary'],
                text="Mixed Mode"
            )
        
        # Ricostruisci tabella
        self._populate_runner_rows()
        self._recalculate()
    
    def _toggle_back(self, selection_id: int):
        """Toggle selezione BACK in modalità Mixed."""
        # Per ora aggiorna solo lo stato visivo
        self._recalculate()
    
    def _toggle_lay(self, selection_id: int):
        """Toggle selezione LAY in modalità Mixed."""
        # Per ora aggiorna solo lo stato visivo
        self._recalculate()
    
    def _toggle_ai_mode(self):
        """Toggle modalità AI Auto-Entry (determina automaticamente BACK/LAY)."""
        new_state = not self._ai_mode_var.get()
        
        if new_state:
            market_type = getattr(self.state, 'market_type', '')
            if not MarketValidator.is_dutching_ready(market_type):
                self._ai_mode_var.set(False)
                self._show_market_warning()
                return
            self._hide_market_warning()
        
        self._ai_mode_var.set(new_state)
        
        if self._ai_mode_var.get():
            self.ai_btn.configure(
                fg_color=COLORS['profit'],
                text="AI: ON"
            )
            self._mixed_mode_var.set(False)
            self.mixed_btn.configure(
                fg_color=COLORS['button_secondary'],
                text="Mixed Mode",
                state="disabled"
            )
        else:
            self.ai_btn.configure(
                fg_color=COLORS['button_secondary'],
                text="AI Auto"
            )
            self.mixed_btn.configure(state="normal")
            self._hide_market_warning()
        
        self._populate_runner_rows()
        self._recalculate()
    
    def _show_market_warning(self):
        """Mostra warning mercato non dutching-ready."""
        if not hasattr(self, '_market_warning_label'):
            self._market_warning_label = ctk.CTkLabel(
                self.window,
                text="",
                font=FONTS['small'],
                text_color="#FF5555"
            )
        self._market_warning_label.configure(
            text="Mercato NON DUTCHING-READY\nAI disabilitata"
        )
        self._market_warning_label.place(relx=0.5, y=10, anchor="n")
    
    def _hide_market_warning(self):
        """Nasconde warning mercato."""
        if hasattr(self, '_market_warning_label'):
            self._market_warning_label.place_forget()
    
    def _on_simulation_toggle(self):
        """Toggle modalità simulazione."""
        sim_mode = self._simulation_var.get()
        
        # Propaga a DutchingState per sincronizzazione backend
        self.state.simulation_mode = sim_mode
        
        # Aggiorna banner simulazione nell'header
        self._update_simulation_banner(sim_mode)
        
        print(f"[Dutching] Simulation mode: {'ON' if sim_mode else 'OFF'}")
    
    def _update_simulation_banner(self, active: bool):
        """Mostra/nasconde banner SIMULATION MODE."""
        if not hasattr(self, '_sim_banner'):
            return
        if active:
            self._sim_banner.configure(text="SIMULATION MODE", text_color="#FF4444")
            self._sim_banner.pack(side=tk.TOP, fill=tk.X, pady=2)
        else:
            self._sim_banner.pack_forget()
    
    def _build_footer(self, parent):
        """Footer con controlli globali."""
        footer_frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_panel'], corner_radius=8)
        footer_frame.pack(fill=tk.X)
        
        # Riga 0: Preset stake + P&L preview
        preset_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        preset_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        
        # Preset stake buttons (25%, 50%, 100%)
        preset_label = ctk.CTkLabel(preset_frame, text="Stake:",
                                   text_color=COLORS['text_secondary'], font=FONTS['small'])
        preset_label.pack(side=tk.LEFT, padx=(0, 5))
        
        for pct in (25, 50, 100):
            btn = ctk.CTkButton(
                preset_frame, text=f"{pct}%",
                command=lambda p=pct: self._set_stake_percent(p),
                fg_color=COLORS['button_secondary'],
                hover_color=COLORS['bg_hover'],
                width=50, height=28
            )
            btn.pack(side=tk.LEFT, padx=2)
        
        # P&L Preview (Net + Worst case)
        self.pnl_preview_label = ctk.CTkLabel(
            preset_frame, text="Net P&L: €0.00 | Worst: €0.00",
            font=FONTS['mono'],
            text_color=COLORS['profit']
        )
        self.pnl_preview_label.pack(side=tk.RIGHT)
        
        # Riga 1: Controlli
        controls_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        controls_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # Live Odds checkbox
        live_check = ctk.CTkCheckBox(
            controls_frame, text="Live Odds",
            variable=self._live_odds_var,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['back'],
            hover_color=COLORS['back_hover']
        )
        live_check.pack(side=tk.LEFT, padx=(0, 15))
        
        # Auto-remove suspended checkbox
        self._auto_remove_var = tk.BooleanVar(value=True)
        auto_remove = ctk.CTkCheckBox(
            controls_frame, text="Auto-remove suspended",
            variable=self._auto_remove_var,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['warning'],
            hover_color=COLORS['warning']
        )
        auto_remove.pack(side=tk.LEFT, padx=(0, 15))
        
        # Global Offset
        offset_label = ctk.CTkLabel(controls_frame, text="Global Offset:",
                                    text_color=COLORS['text_primary'])
        offset_label.pack(side=tk.LEFT, padx=(0, 5))
        
        offset_entry = ctk.CTkEntry(
            controls_frame, textvariable=self._global_offset_var,
            width=50, font=FONTS['small'],
            fg_color=COLORS['bg_surface'],
            text_color=COLORS['text_primary'],
            justify="center"
        )
        offset_entry.pack(side=tk.LEFT, padx=(0, 15))
        offset_entry.bind('<Return>', self._on_global_offset_change)
        
        # Swap All checkbox
        swap_all = ctk.CTkCheckBox(
            controls_frame, text="Swap All",
            variable=self._swap_all_var,
            command=self._on_swap_all,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['lay'],
            hover_color=COLORS['lay_hover']
        )
        swap_all.pack(side=tk.LEFT, padx=(0, 15))
        
        # Auto-Green checkbox (PRO)
        auto_green = ctk.CTkCheckBox(
            controls_frame, text="Auto-Green",
            variable=self._auto_green_var,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['profit'],
            hover_color=COLORS['button_success']
        )
        auto_green.pack(side=tk.LEFT, padx=(0, 15))
        
        # Simulation Mode checkbox
        sim_check = ctk.CTkCheckBox(
            controls_frame, text="SIM",
            variable=self._simulation_var,
            command=self._on_simulation_toggle,
            text_color=COLORS['text_primary'],
            fg_color=COLORS['warning'],
            hover_color=COLORS['warning']
        )
        sim_check.pack(side=tk.LEFT, padx=(0, 15))
        
        # Total label
        self.total_label = ctk.CTkLabel(
            controls_frame, text="Total: €0.00",
            font=FONTS['heading'],
            text_color=COLORS['back']
        )
        self.total_label.pack(side=tk.RIGHT)
        
        # Riga 2: Pulsanti
        buttons_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        buttons_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        # Select All
        select_all_btn = ctk.CTkButton(
            buttons_frame, text="Select All",
            command=self._select_all,
            fg_color=COLORS['button_secondary'],
            hover_color=COLORS['bg_hover'],
            width=100
        )
        select_all_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Select None
        select_none_btn = ctk.CTkButton(
            buttons_frame, text="Select None",
            command=self._select_none,
            fg_color=COLORS['button_secondary'],
            hover_color=COLORS['bg_hover'],
            width=100
        )
        select_none_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Refresh Odds
        refresh_btn = ctk.CTkButton(
            buttons_frame, text="Refresh Odds",
            command=self._refresh_odds,
            fg_color=COLORS['info'],
            hover_color=COLORS['info_hover'],
            width=120
        )
        refresh_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Spacer
        spacer = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Cancel
        cancel_btn = ctk.CTkButton(
            buttons_frame, text="Cancel",
            command=self._on_cancel,
            fg_color=COLORS['button_secondary'],
            hover_color=COLORS['bg_hover'],
            width=100
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Submit
        self.submit_btn = ctk.CTkButton(
            buttons_frame, text="Submit",
            command=self._on_submit,
            fg_color=COLORS['profit'],
            hover_color=COLORS['button_success'],
            width=120
        )
        self.submit_btn.pack(side=tk.RIGHT)
    
    # === EVENT HANDLERS ===
    
    def _on_mode_change(self):
        """Cambio modalità dutching."""
        mode = self._mode_var.get()
        self.state.mode = DutchingMode.STAKE_AVAILABLE if mode == "stake" else DutchingMode.REQUIRED_PROFIT
        self._recalculate()
    
    def _on_auto_ratio_change(self):
        """Toggle auto ratio."""
        self.state.auto_ratio = self._auto_ratio_var.get()
        self._recalculate()
    
    def _toggle_runner(self, selection_id: int):
        """Toggle inclusione runner."""
        self.state.toggle_included(selection_id)
        self._recalculate()
    
    def _toggle_swap(self, selection_id: int):
        """Toggle BACK/LAY."""
        self.state.toggle_swap(selection_id)
        self._recalculate()
    
    def _adjust_offset(self, selection_id: int, delta: int):
        """Adjust offset tick."""
        for r in self.state.runners:
            if r.selection_id == selection_id:
                new_offset = r.offset + delta
                self.state.set_offset(selection_id, new_offset)
                self._runner_offset_vars[selection_id].set(str(new_offset))
                break
        self._recalculate()
    
    def _on_odds_change(self, selection_id: int):
        """Cambio manuale quota."""
        try:
            new_odds = float(self._runner_odds_vars[selection_id].get())
            if new_odds >= 1.01:
                self.state.set_odds(selection_id, new_odds)
                self._recalculate()
        except ValueError:
            pass
    
    def _on_global_offset_change(self, event=None):
        """Cambio offset globale."""
        try:
            offset = int(self._global_offset_var.get())
            self.state.global_offset = offset
            # Update tutti gli offset vars
            for sel_id in self._runner_offset_vars:
                self._runner_offset_vars[sel_id].set(str(offset))
            self._recalculate()
        except ValueError:
            pass
    
    def _on_swap_all(self):
        """Swap all BACK/LAY."""
        self.state.swap_all()
        # Update swap vars
        for runner in self.state.runners:
            if runner.selection_id in self._runner_swap_vars:
                self._runner_swap_vars[runner.selection_id].set(runner.swap)
        self._recalculate()
    
    def _select_all(self):
        """Seleziona tutti."""
        self.state.select_all()
        for runner in self.state.runners:
            if runner.selection_id in self._runner_checkboxes:
                self._runner_checkboxes[runner.selection_id].set(runner.included)
        self._recalculate()
    
    def _select_none(self):
        """Deseleziona tutti."""
        self.state.select_none()
        for sel_id in self._runner_checkboxes:
            self._runner_checkboxes[sel_id].set(False)
        self._recalculate()
    
    def _refresh_odds(self):
        """Aggiorna quote live."""
        if self.on_refresh_odds:
            self.on_refresh_odds()
    
    def _on_cancel(self):
        """Chiudi finestra."""
        self.window.destroy()
    
    def _on_submit(self):
        """Submit ordini."""
        orders = self.state.get_orders_to_place()
        
        if not orders:
            messagebox.showwarning("Attenzione", "Nessun ordine da piazzare.", parent=self.window)
            return
        
        # Validazione
        errors = validate_selections(
            [{'runnerName': o['runnerName'], 'stake': o['size'], 'price': o['price']} for o in orders],
            bet_type='BACK'
        )
        
        if errors:
            messagebox.showerror("Errori Validazione", "\n".join(errors), parent=self.window)
            return
        
        # Conferma
        total = sum(o['size'] for o in orders)
        auto_green = self._auto_green_var.get()
        sim_mode = self._simulation_var.get()
        
        mode_text = " [SIM]" if sim_mode else ""
        green_text = " + Auto-Green" if auto_green else ""
        msg = f"Piazzare {len(orders)} ordini per totale €{total:.2f}{mode_text}{green_text}?"
        
        if messagebox.askyesno("Conferma", msg, parent=self.window):
            # Aggiungi metadata agli ordini
            import time
            placed_at = time.time()
            for order in orders:
                order['auto_green'] = auto_green
                order['simulation'] = sim_mode
                order['market_id'] = self.state.market_id
                order['placed_at'] = placed_at
            
            if sim_mode:
                # Simulation mode: non inviare a Betfair, solo log
                print(f"[Dutching] SIMULATION: {len(orders)} ordini simulati per €{total:.2f}")
                for o in orders:
                    print(f"  [SIM] {o['side']} {o['runnerName']} @ {o['price']} €{o['size']:.2f}")
                messagebox.showinfo(
                    "Simulazione", 
                    f"Ordini SIMULATI piazzati: {len(orders)} per €{total:.2f}\n"
                    "Nessun ordine reale inviato a Betfair.",
                    parent=self.window
                )
            else:
                # Ordini reali
                self.on_submit(orders)
                
                if auto_green:
                    print(f"[Dutching] Auto-Green attivo - monitoring P&L per green-up automatico")
            
            self.window.destroy()
    
    def _on_state_change(self):
        """Callback da DutchingState - ricalcola."""
        if self.state.auto_ratio:
            self._recalculate()
    
    def _recalculate(self):
        """Ricalcola stake e aggiorna UI."""
        # Reset highlight prima di ogni ricalcolo per evitare highlight stale
        self._reset_all_highlights()
        
        try:
            # Leggi parametri
            mode = self._mode_var.get()
            
            if mode == "stake":
                try:
                    total = float(self._stake_var.get())
                except ValueError:
                    total = 100.0
                self.state._total_stake = total
            else:
                try:
                    profit = float(self._profit_var.get())
                except ValueError:
                    profit = 10.0
                self.state._target_profit = profit
            
            # Ottieni selezioni
            selections = self.state.get_selections_for_engine()
            
            if not selections:
                self._update_totals(0, 0)
                return
            
            # Determina se mixed
            has_back = any(s['effectiveType'] == 'BACK' for s in selections)
            has_lay = any(s['effectiveType'] == 'LAY' for s in selections)
            
            if mode == "stake":
                total_stake = self.state.total_stake
            else:
                # Per Required Profit, calcola stake necessario
                # Semplificazione: usa formula base
                avg_odds = sum(s['price'] for s in selections) / len(selections)
                total_stake = self.state.target_profit / (avg_odds - 1) * len(selections)
            
            # Calcola - AI mode usa calcolo automatico BACK/LAY
            if self._ai_mode_var.get():
                # AI Auto-Entry: determina automaticamente BACK/LAY per ogni runner
                results, avg_profit, book = calculate_ai_mixed_stakes(
                    selections, total_stake, self.state.commission, MIN_STAKE
                )
                # Aggiorna stato runner con side determinato da AI
                for r in results:
                    for runner in self.state.runners:
                        if runner.selection_id == r['selectionId']:
                            runner.swap = (r['effectiveType'] == 'LAY')
                            break
            elif has_back and has_lay:
                results, avg_profit, book = calculate_mixed_dutching(
                    selections, total_stake, self.state.commission
                )
            elif has_lay and not has_back:
                results, avg_profit, book = calculate_dutching_stakes(
                    selections, total_stake, 'LAY', self.state.commission
                )
            else:
                results, avg_profit, book = calculate_dutching_stakes(
                    selections, total_stake, 'BACK', self.state.commission
                )
            
            # Applica risultati
            self.state.apply_calculation_results(results)
            
            # Aggiorna UI
            self._update_runner_display()
            self._update_totals(self.state.get_total_stake(), book)
            self._highlight_best_odds()
            self._update_pnl_preview()
            
        except Exception as e:
            print(f"[Dutching] Errore calcolo: {e}")
            self._update_totals(0, 0)
    
    def _update_runner_display(self):
        """Aggiorna display righe runner."""
        ai_mode_active = self._ai_mode_var.get()
        
        for runner in self.state.runners:
            sel_id = runner.selection_id
            
            if sel_id not in self._runner_widgets:
                continue
            
            widgets = self._runner_widgets[sel_id]
            
            # Stake
            stake_text = f"€{runner.stake:.2f}" if runner.included else "€0"
            widgets['stake_label'].configure(text=stake_text)
            
            # Profit
            profit = runner.profit_if_wins
            total_stake = self.state.get_total_stake()
            
            if runner.included:
                profit_color = COLORS['profit'] if profit >= 0 else COLORS['loss']
                profit_text = f"€{profit:.2f}"
            else:
                profit_color = COLORS['loss']
                profit_text = f"-€{total_stake:.2f}"
            
            widgets['profit_label'].configure(text=profit_text, text_color=profit_color)
            
            # Nome con badge AI se attivo
            if ai_mode_active and runner.included:
                side_badge = "[LAY]" if runner.swap else "[BACK]"
                name_display = f"{runner.runner_name} {side_badge}"
                name_color = COLORS['lay'] if runner.swap else COLORS['back']
            else:
                name_display = runner.runner_name
                name_color = COLORS['text_primary'] if runner.included else COLORS['text_tertiary']
            
            widgets['name_label'].configure(text=name_display, text_color=name_color)
            
            # Odds colore
            odds_color = COLORS['lay'] if runner.swap else COLORS['back']
            widgets['odds_entry'].configure(text_color=odds_color)
    
    def _set_stake_percent(self, percent: int):
        """Imposta stake come percentuale dello stake corrente."""
        try:
            current = float(self._stake_var.get())
        except ValueError:
            current = 100.0
        
        # Usa lo stake base (100) se non impostato
        base_stake = 100.0 if current < 10 else current
        new_stake = base_stake * percent / 100
        self._stake_var.set(f"{new_stake:.2f}")
        self._mode_var.set("stake")
        self._recalculate()
    
    def _reset_all_highlights(self):
        """Reset tutti gli highlight quote prima di ricalcolo."""
        for runner in self.state.runners:
            sel_id = runner.selection_id
            if sel_id not in self._runner_widgets:
                continue
            widgets = self._runner_widgets[sel_id]
            if 'odds_entry' in widgets:
                try:
                    widgets['odds_entry'].configure(border_color=COLORS['border'], border_width=1)
                except Exception:
                    pass
    
    def _find_best_odds(self):
        """Trova runner con migliore quota (BACK=max, LAY=min)."""
        best_back = None
        best_lay = None
        
        # Cerca tra tutti i runner inclusi
        for runner in self.state.runners:
            if not runner.included:
                continue
            if runner.effective_type == 'BACK':
                if best_back is None or runner.effective_odds > best_back.effective_odds:
                    best_back = runner
            else:  # LAY
                if best_lay is None or runner.effective_odds < best_lay.effective_odds:
                    best_lay = runner
        
        return best_back, best_lay
    
    def _highlight_best_odds(self):
        """Evidenzia runner con migliore quota (funziona anche con AI mode)."""
        # Trova migliori quote tra runner inclusi
        best_back, best_lay = self._find_best_odds()
        
        for runner in self.state.runners:
            sel_id = runner.selection_id
            if sel_id not in self._runner_widgets:
                continue
            
            widgets = self._runner_widgets[sel_id]
            
            # Verifica se è il migliore
            is_best = (runner == best_back or runner == best_lay)
            
            # Applica highlight solo se odds_entry esiste (modalità normale e AI)
            if 'odds_entry' in widgets:
                try:
                    if is_best and runner.included:
                        widgets['odds_entry'].configure(border_color=COLORS['profit'], border_width=2)
                    else:
                        widgets['odds_entry'].configure(border_color=COLORS['border'], border_width=1)
                except Exception:
                    pass  # Widget potrebbe non esistere più
    
    def _update_pnl_preview(self):
        """Aggiorna preview P&L netto e worst case."""
        included = self.state.included_runners
        total_stake = self.state.get_total_stake()
        
        if not included or total_stake <= 0:
            self.pnl_preview_label.configure(
                text="Net P&L: €0.00 | Worst: -€0.00",
                text_color=COLORS['text_secondary']
            )
            return
        
        # Profitti per ogni scenario (se quel runner vince)
        profits = [r.profit_if_wins for r in included if r.stake > 0]
        
        if not profits:
            self.pnl_preview_label.configure(
                text="Net P&L: €0.00 | Worst: -€0.00",
                text_color=COLORS['text_secondary']
            )
            return
        
        # Profitto garantito = minimo tra tutti i profitti (dutching uniforme)
        guaranteed_profit = min(profits)
        
        # Worst case = se nessuna vince (perdi tutto lo stake)
        worst_case = -total_stake
        
        # Colore basato sul profitto garantito
        if guaranteed_profit > 0:
            color = COLORS['profit']
            pnl_text = f"+€{guaranteed_profit:.2f}"
        elif guaranteed_profit >= 0:
            color = COLORS['text_primary']
            pnl_text = f"€{guaranteed_profit:.2f}"
        else:
            color = COLORS['loss']
            pnl_text = f"-€{abs(guaranteed_profit):.2f}"
        
        self.pnl_preview_label.configure(
            text=f"Guaranteed: {pnl_text} | Loss: -€{total_stake:.2f}",
            text_color=color
        )
    
    def _update_totals(self, total_stake: float, book_value: float):
        """Aggiorna totali footer con warning book > 105%."""
        self.total_label.configure(text=f"Total: €{total_stake:.2f}")
        
        # Verifica selezioni minime
        included_count = len(self.state.included_runners)
        has_valid_selections = included_count >= 2 and total_stake >= 2.0
        
        # Warning book value (usa costanti configurabili)
        if book_value > BOOK_BLOCK:
            book_text = f"Book: {book_value:.1f}%"
            book_color = COLORS['loss']
            can_submit = False
        elif book_value > BOOK_WARNING:
            book_text = f"Book: {book_value:.1f}%"
            book_color = COLORS['warning']
            can_submit = has_valid_selections
        elif book_value > 0:
            book_text = f"Book: {book_value:.1f}%"
            book_color = COLORS['profit'] if book_value < 100 else COLORS['text_primary']
            can_submit = has_valid_selections
        else:
            book_text = "Book: --%"
            book_color = COLORS['text_tertiary']
            can_submit = False
        
        self.book_label.configure(text=book_text, text_color=book_color)
        self.submit_btn.configure(state=tk.NORMAL if can_submit else tk.DISABLED)
        
        # Aggiorna highlight e P&L preview
        self._highlight_best_odds()
        self._update_pnl_preview()


def open_dutching_window(parent, market_data: Dict, runners: List[Dict],
                         on_submit: Callable, on_refresh: Optional[Callable] = None):
    """
    Helper per aprire finestra dutching.
    
    Args:
        parent: Finestra padre
        market_data: {'marketId', 'marketName', 'eventName', 'startTime', 'status'}
        runners: [{'selectionId', 'runnerName', 'price'}]
        on_submit: Callback(orders: List[Dict])
        on_refresh: Callback per refresh odds
    """
    state = DutchingState()
    
    state.set_market_info(
        market_id=market_data.get('marketId', ''),
        market_name=market_data.get('marketName', ''),
        event_name=market_data.get('eventName', ''),
        start_time=market_data.get('startTime', ''),
        status=market_data.get('status', 'OPEN')
    )
    
    state.load_runners(runners)
    
    window = DutchingConfirmationWindow(
        parent=parent,
        state=state,
        on_submit=on_submit,
        on_refresh_odds=on_refresh
    )
    
    return window
