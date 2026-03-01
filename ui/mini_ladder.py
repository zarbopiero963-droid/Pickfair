"""
MiniLadder - Mini ladder inline PRO per dutching UI

Mostra 3 livelli BACK/LAY per ogni runner con highlight del best price.
Stile professionale tipo Bet Angel.

v3.65 - One-Click Actions con preflight automatico
v3.68 - UI Indicator liquidita (dot colorato + tooltip)
"""

import customtkinter as ctk
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

from theme import COLORS
from safety_logger import evaluate_runner_liquidity, LiquidityStatus

if TYPE_CHECKING:
    from controllers.dutching_controller import DutchingController


class MiniLadder(ctk.CTkFrame):
    """
    Mini ladder inline che mostra 3 livelli BACK e LAY.
    
    Features:
    - Best price evidenziato con bordo verde
    - Click su prezzo per selezione rapida
    - Aggiornamento real-time via update_prices()
    - Liquidity indicator (dot colorato verde/giallo/rosso) v3.68
    """
    
    def __init__(
        self, 
        parent, 
        runner: Dict,
        on_price_click: Optional[Callable] = None,
        levels: int = 3,
        stake: float = 0.0,
        side: str = "BACK"
    ):
        """
        Args:
            parent: Widget parent
            runner: Dict con runnerName, selectionId, back_ladder, lay_ladder
            on_price_click: Callback(selection_id, side, price) su click prezzo
            levels: Numero livelli da mostrare (default 3)
            stake: Stake previsto per questo runner (per indicator liquidita)
            side: Tipo scommessa BACK/LAY per valutazione liquidita
        """
        super().__init__(parent, fg_color="transparent")
        
        self.runner = runner
        self.on_price_click = on_price_click
        self.levels = levels
        self.stake = stake
        self.side = side
        
        self.back_labels = []
        self.lay_labels = []
        self.liquidity_indicator = None
        
        self._build()
    
    def _build(self):
        """Costruisce UI della mini ladder."""
        # Header con nome runner + liquidity indicator
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 2))
        
        ctk.CTkLabel(
            header,
            text=self.runner.get("runnerName", "Runner"),
            font=("Roboto", 12, "bold"),
            anchor="w"
        ).pack(side="left", fill="x", expand=True)
        
        # Liquidity indicator (dot colorato)
        self.liquidity_indicator = ctk.CTkLabel(
            header,
            text="",
            width=12,
            height=12,
            corner_radius=6,
            fg_color="#4CAF50"
        )
        self.liquidity_indicator.pack(side="right", padx=4)
        
        # Aggiorna indicator iniziale
        self._update_liquidity_indicator()
        
        # Container prezzi
        prices_frame = ctk.CTkFrame(self, fg_color=COLORS.get("bg_secondary", "#2b2b2b"))
        prices_frame.pack(fill="x")
        
        # Colonna BACK (sinistra)
        back_col = ctk.CTkFrame(prices_frame, fg_color="transparent")
        back_col.pack(side="left", expand=True, fill="both", padx=1)
        
        ctk.CTkLabel(
            back_col,
            text="BACK",
            font=("Roboto", 9),
            text_color=COLORS.get("back", "#1e88e5")
        ).pack()
        
        # Crea label per livelli BACK
        for i in range(self.levels):
            lbl = ctk.CTkLabel(
                back_col,
                text="-",
                font=("Roboto", 10),
                fg_color=COLORS.get("back_bg", "#1e3a5f"),
                corner_radius=3,
                width=70,
                height=22
            )
            lbl.pack(pady=1)
            lbl.bind("<Button-1>", lambda e, idx=i: self._on_back_click(idx))
            self.back_labels.append(lbl)
        
        # Colonna LAY (destra)
        lay_col = ctk.CTkFrame(prices_frame, fg_color="transparent")
        lay_col.pack(side="left", expand=True, fill="both", padx=1)
        
        ctk.CTkLabel(
            lay_col,
            text="LAY",
            font=("Roboto", 9),
            text_color=COLORS.get("lay", "#e5399b")
        ).pack()
        
        # Crea label per livelli LAY
        for i in range(self.levels):
            lbl = ctk.CTkLabel(
                lay_col,
                text="-",
                font=("Roboto", 10),
                fg_color=COLORS.get("lay_bg", "#5f1e3a"),
                corner_radius=3,
                width=70,
                height=22
            )
            lbl.pack(pady=1)
            lbl.bind("<Button-1>", lambda e, idx=i: self._on_lay_click(idx))
            self.lay_labels.append(lbl)
        
        # Aggiorna con dati iniziali
        self.update_prices(self.runner)
    
    def update_prices(self, runner: Dict):
        """
        Aggiorna prezzi visualizzati.
        
        Args:
            runner: Dict con back_ladder e lay_ladder aggiornati
        """
        self.runner = runner
        
        back_ladder = runner.get("back_ladder", [])[:self.levels]
        lay_ladder = runner.get("lay_ladder", [])[:self.levels]
        
        # Best prices
        best_back = back_ladder[0]["price"] if back_ladder else None
        best_lay = lay_ladder[0]["price"] if lay_ladder else None
        
        # Aggiorna BACK labels
        for i, lbl in enumerate(self.back_labels):
            if i < len(back_ladder):
                p = back_ladder[i]
                price = p.get("price", 0)
                size = p.get("size", 0)
                lbl.configure(text=f"{price:.2f} (€{size:.0f})")
                
                # Highlight best price
                if price == best_back:
                    lbl.configure(
                        fg_color=COLORS.get("back", "#1e88e5"),
                        text_color="white"
                    )
                else:
                    lbl.configure(
                        fg_color=COLORS.get("back_bg", "#1e3a5f"),
                        text_color=COLORS.get("text", "#ffffff")
                    )
            else:
                lbl.configure(text="-")
                lbl.configure(
                    fg_color=COLORS.get("back_bg", "#1e3a5f"),
                    text_color=COLORS.get("text_secondary", "#888888")
                )
        
        # Aggiorna LAY labels
        for i, lbl in enumerate(self.lay_labels):
            if i < len(lay_ladder):
                p = lay_ladder[i]
                price = p.get("price", 0)
                size = p.get("size", 0)
                lbl.configure(text=f"{price:.2f} (€{size:.0f})")
                
                # Highlight best price
                if price == best_lay:
                    lbl.configure(
                        fg_color=COLORS.get("lay", "#e5399b"),
                        text_color="white"
                    )
                else:
                    lbl.configure(
                        fg_color=COLORS.get("lay_bg", "#5f1e3a"),
                        text_color=COLORS.get("text", "#ffffff")
                    )
            else:
                lbl.configure(text="-")
                lbl.configure(
                    fg_color=COLORS.get("lay_bg", "#5f1e3a"),
                    text_color=COLORS.get("text_secondary", "#888888")
                )
        
        # Aggiorna indicator liquidita con nuovi dati ladder
        self._update_liquidity_indicator()
    
    def _on_back_click(self, index: int):
        """Handler click su prezzo BACK."""
        if not self.on_price_click:
            return
        
        back_ladder = self.runner.get("back_ladder", [])
        if index < len(back_ladder):
            price = back_ladder[index].get("price", 0)
            self.on_price_click(
                self.runner.get("selectionId"),
                "BACK",
                price
            )
    
    def _on_lay_click(self, index: int):
        """Handler click su prezzo LAY."""
        if not self.on_price_click:
            return
        
        lay_ladder = self.runner.get("lay_ladder", [])
        if index < len(lay_ladder):
            price = lay_ladder[index].get("price", 0)
            self.on_price_click(
                self.runner.get("selectionId"),
                "LAY",
                price
            )
    
    def set_highlight(self, side: str, enabled: bool = True):
        """
        Evidenzia un lato (per mostrare selezione AI).
        
        Args:
            side: 'BACK' o 'LAY'
            enabled: True per evidenziare
        """
        if side == "BACK":
            for lbl in self.back_labels:
                if enabled:
                    lbl.configure(border_width=2, border_color="#00ff00")
                else:
                    lbl.configure(border_width=0)
        else:
            for lbl in self.lay_labels:
                if enabled:
                    lbl.configure(border_width=2, border_color="#00ff00")
                else:
                    lbl.configure(border_width=0)
    
    def _update_liquidity_indicator(self):
        """Aggiorna il dot colorato in base alla liquidita disponibile."""
        if not self.liquidity_indicator:
            return
        
        # Ottieni liquidita e prezzo dal ladder corretto per il side
        back_ladder = self.runner.get("back_ladder", [])
        lay_ladder = self.runner.get("lay_ladder", [])
        
        if self.side == "BACK":
            ladder = back_ladder
            available_liq = sum(p.get("size", 0) for p in back_ladder)
            price = back_ladder[0].get("price", 1.0) if back_ladder else 1.0
        else:
            ladder = lay_ladder
            available_liq = sum(p.get("size", 0) for p in lay_ladder)
            price = lay_ladder[0].get("price", 1.0) if lay_ladder else 1.0
        
        # Valuta status liquidita (usa stesse soglie del Liquidity Guard)
        result = evaluate_runner_liquidity(
            stake=self.stake,
            available_liquidity=available_liq,
            side=self.side,
            price=price
        )
        
        # Aggiorna colore dot
        self.liquidity_indicator.configure(fg_color=result["color"])
        
        # Tooltip simulato (CustomTkinter non ha tooltip nativo)
        self._liq_tooltip = result["tooltip"]
    
    def set_stake(self, stake: float, side: str = None):
        """
        Aggiorna stake e ricalcola indicator liquidita.
        
        Args:
            stake: Nuovo stake previsto
            side: Nuovo side (opzionale)
        """
        self.stake = stake
        if side:
            self.side = side
        self._update_liquidity_indicator()
    
    def update_liquidity(self, stake: float, side: str = "BACK"):
        """
        Aggiorna indicator liquidita con nuovi parametri.
        
        Args:
            stake: Stake per valutazione
            side: BACK o LAY
        """
        self.stake = stake
        self.side = side
        self._update_liquidity_indicator()
    
    def set_edge_badge(self, edge_score: float, confidence: float):
        """
        Mostra badge edge AI sotto la ladder.
        
        Args:
            edge_score: Score [-1, 1] dove + = BACK, - = LAY
            confidence: Confidenza [0, 1]
        """
        if not hasattr(self, "_edge_badge"):
            self._edge_badge = ctk.CTkLabel(
                self,
                text="",
                font=("Roboto", 9),
                corner_radius=3,
                width=60,
                height=18
            )
            self._edge_badge.pack(pady=(2, 0))
        
        if abs(edge_score) < 0.1:
            self._edge_badge.configure(
                text=f"NEUTRAL {confidence:.0%}",
                fg_color=COLORS.get("bg_tertiary", "#444444"),
                text_color=COLORS.get("text_secondary", "#888888")
            )
        elif edge_score > 0:
            strength = "STRONG " if edge_score > 0.5 else ""
            self._edge_badge.configure(
                text=f"{strength}BACK {confidence:.0%}",
                fg_color=COLORS.get("back", "#1e88e5"),
                text_color="white"
            )
        else:
            strength = "STRONG " if edge_score < -0.5 else ""
            self._edge_badge.configure(
                text=f"{strength}LAY {confidence:.0%}",
                fg_color=COLORS.get("lay", "#e5399b"),
                text_color="white"
            )


class OneClickLadder(MiniLadder):
    """
    MiniLadder con supporto one-click order.
    
    Click su best price:
    1. Esegue preflight_check automatico
    2. Piazza ordine singolo (non dutching) se preflight OK
    3. Attiva Auto-Green se toggle abilitato
    """
    
    def __init__(
        self,
        parent,
        runner: Dict,
        controller: Optional["DutchingController"] = None,
        market_id: str = "",
        market_type: str = "MATCH_ODDS",
        default_stake: float = 10.0,
        auto_green: bool = False,
        on_order_result: Optional[Callable] = None,
        **kwargs
    ):
        """
        Args:
            controller: DutchingController per piazzamento ordini
            market_id: ID mercato Betfair
            market_type: Tipo mercato
            default_stake: Stake default per one-click
            auto_green: Se abilitare auto-green
            on_order_result: Callback(result_dict) dopo piazzamento
        """
        self.controller = controller
        self.market_id = market_id
        self.market_type = market_type
        self.default_stake = default_stake
        self.auto_green_enabled = auto_green
        self.on_order_result = on_order_result
        
        super().__init__(parent, runner, on_price_click=self._handle_one_click, **kwargs)
    
    def _handle_one_click(self, selection_id: int, side: str, price: float):
        """
        Gestisce one-click order.
        
        Args:
            selection_id: ID runner
            side: 'BACK' o 'LAY'
            price: Prezzo cliccato
        """
        if not self.controller:
            return
        
        selection = {
            "selectionId": selection_id,
            "runnerName": self.runner.get("runnerName", f"Runner {selection_id}"),
            "price": price,
            "back_ladder": self.runner.get("back_ladder", []),
            "lay_ladder": self.runner.get("lay_ladder", [])
        }
        
        result = self.controller.submit_dutching(
            market_id=self.market_id,
            market_type=self.market_type,
            selections=[selection],
            total_stake=self.default_stake,
            mode=side,
            ai_enabled=False,
            auto_green=self.auto_green_enabled,
            dry_run=False
        )
        
        if self.on_order_result:
            self.on_order_result(result)
    
    def set_default_stake(self, stake: float):
        """Imposta stake default per one-click."""
        self.default_stake = stake
    
    def set_auto_green(self, enabled: bool):
        """Abilita/disabilita auto-green per one-click."""
        self.auto_green_enabled = enabled


class LiveMiniLadder(ctk.CTkFrame):
    """
    Versione live della MiniLadder con:
    - Aggiornamento automatico ogni 500ms
    - Badge [BACK]/[LAY] da AI WoM
    - P&L preview inline
    - Highlight miglior quota
    
    v3.66 - Live updates con edge badge
    """
    
    def __init__(
        self,
        parent,
        selections: List[Dict],
        controller: Optional["DutchingController"] = None,
        refresh_interval: int = 500,
        **kwargs
    ):
        """
        Args:
            selections: Lista selezioni iniziali
            controller: DutchingController per WoM e P&L
            refresh_interval: Intervallo refresh in ms (default 500)
        """
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        self.selections = selections
        self.controller = controller
        self.refresh_interval = refresh_interval
        
        self.runner_frames = {}
        self.name_labels = {}
        self.badge_labels = {}
        self.pnl_labels = {}
        self.price_buttons = {}
        
        self._is_running = True
        self._build()
        self._start_refresh()
    
    def _build(self):
        """Costruisce UI per ogni runner."""
        for idx, sel in enumerate(self.selections):
            sel_id = sel.get("selectionId", idx)
            
            frame = ctk.CTkFrame(self, fg_color=COLORS.get("bg_secondary", "#2b2b2b"))
            frame.pack(fill="x", pady=2, padx=2)
            
            name_lbl = ctk.CTkLabel(
                frame,
                text=sel.get("runnerName", f"Runner {sel_id}"),
                font=("Roboto", 11),
                anchor="w",
                width=120
            )
            name_lbl.pack(side="left", padx=4)
            
            side = sel.get("side", "BACK")
            badge_color = COLORS.get("back", "#1e88e5") if side == "BACK" else COLORS.get("lay", "#e5399b")
            badge_lbl = ctk.CTkLabel(
                frame,
                text=f"[{side}]",
                font=("Roboto", 10, "bold"),
                fg_color=badge_color,
                corner_radius=3,
                width=50,
                text_color="white"
            )
            badge_lbl.pack(side="left", padx=4)
            
            price = sel.get("price", 2.0)
            price_btn = ctk.CTkButton(
                frame,
                text=f"{price:.2f}",
                font=("Roboto", 11),
                width=60,
                height=26,
                fg_color=COLORS.get("bg_tertiary", "#3d3d3d"),
                hover_color=COLORS.get("back", "#1e88e5"),
                command=lambda s=sel: self._on_price_click(s)
            )
            price_btn.pack(side="left", padx=4)
            
            pnl_lbl = ctk.CTkLabel(
                frame,
                text="P&L: 0.00",
                font=("Roboto", 10),
                text_color=COLORS.get("text_secondary", "#888888"),
                width=80
            )
            pnl_lbl.pack(side="right", padx=4)
            
            self.runner_frames[sel_id] = frame
            self.name_labels[sel_id] = name_lbl
            self.badge_labels[sel_id] = badge_lbl
            self.pnl_labels[sel_id] = pnl_lbl
            self.price_buttons[sel_id] = price_btn
    
    def _start_refresh(self):
        """Avvia ciclo di refresh."""
        if self._is_running:
            self._refresh()
            self.after(self.refresh_interval, self._start_refresh)
    
    def _refresh(self):
        """Aggiorna quote, badge e P&L."""
        if not self.controller or not self.selections:
            return
        
        edge_scores = {}
        if hasattr(self.controller, 'wom_engine') and self.controller.wom_engine:
            try:
                edge_scores = self.controller.wom_engine.get_ai_edge_score(self.selections)
            except Exception:
                pass
        
        best_price_sel = max(self.selections, key=lambda x: x.get("price", 0))
        best_sel_id = best_price_sel.get("selectionId")
        
        for sel in self.selections:
            sel_id = sel.get("selectionId")
            if sel_id not in self.badge_labels:
                continue
            
            edge = edge_scores.get(sel_id)
            if edge:
                side = edge.suggested_side if hasattr(edge, 'suggested_side') else edge.get('side', 'BACK')
            else:
                side = sel.get("side", "BACK")
            
            sel["side"] = side
            
            badge_color = COLORS.get("back", "#1e88e5") if side == "BACK" else COLORS.get("lay", "#e5399b")
            self.badge_labels[sel_id].configure(text=f"[{side}]", fg_color=badge_color)
            
            pnl = 0.0
            if hasattr(self.controller, 'pnl_engine') and self.controller.pnl_engine:
                try:
                    pnl = self.controller.pnl_engine.calculate_preview(sel, side)
                except Exception:
                    pass
            
            pnl_color = COLORS.get("profit", "#4caf50") if pnl >= 0 else COLORS.get("loss", "#f44336")
            self.pnl_labels[sel_id].configure(
                text=f"P&L: {pnl:.2f}",
                text_color=pnl_color
            )
            
            if sel_id == best_sel_id:
                self.name_labels[sel_id].configure(
                    fg_color=COLORS.get("warning", "#ff9800"),
                    corner_radius=3
                )
            else:
                self.name_labels[sel_id].configure(fg_color="transparent")
    
    def _on_price_click(self, selection: Dict):
        """Handler click su prezzo per one-click order."""
        if not self.controller:
            return
        
        result = self.controller.submit_dutching(
            market_id=selection.get("marketId", ""),
            market_type=selection.get("marketType", "MATCH_ODDS"),
            selections=[selection],
            total_stake=selection.get("presetStake", 5.0),
            mode=selection.get("side", "BACK"),
            ai_enabled=True,
            dry_run=False
        )
        print(f"One-click order result: {result}")
    
    def update_selections(self, selections: List[Dict]):
        """Aggiorna lista selezioni."""
        self.selections = selections
    
    def stop(self):
        """Ferma il refresh loop."""
        self._is_running = False
    
    def start(self):
        """Riavvia il refresh loop."""
        self._is_running = True
        self._start_refresh()
