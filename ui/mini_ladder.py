"""
Mini Ladder UI component.

Componente UI disaccoppiato.
Non esegue ordini direttamente.
Pubblica soltanto intenti REQ_QUICK_BET sull'EventBus.
"""

import customtkinter as ctk

from theme import COLORS
from ui.tk_safe import messagebox, tk


class MiniLadder(ctk.CTkFrame):
    def __init__(self, master, app, event_bus, market_data, selection_data, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.app = app
        self.bus = event_bus
        self.market_data = market_data or {}
        self.selection_data = selection_data or {}

        self.header = None
        self.grid_frame = None
        self.btn_back = None
        self.btn_lay = None

        self._build_ui()

    def _extract_back_price(self, data):
        price = data.get("backPrice")
        if isinstance(price, int | float) and price > 0:
            return float(price)

        back_prices = data.get("backPrices", [])
        if back_prices and isinstance(back_prices, list):
            first = back_prices[0]
            if isinstance(first, list | tuple) and first:
                try:
                    return float(first[0])
                except Exception:
                    return 0.0
            if isinstance(first, dict):
                try:
                    return float(first.get("price", 0.0))
                except Exception:
                    return 0.0

        back_ladder = data.get("back_ladder", [])
        if back_ladder and isinstance(back_ladder, list):
            first = back_ladder[0]
            if isinstance(first, dict):
                try:
                    return float(first.get("price", 0.0))
                except Exception:
                    return 0.0

        return 0.0

    def _extract_lay_price(self, data):
        price = data.get("layPrice")
        if isinstance(price, int | float) and price > 0:
            return float(price)

        lay_prices = data.get("layPrices", [])
        if lay_prices and isinstance(lay_prices, list):
            first = lay_prices[0]
            if isinstance(first, list | tuple) and first:
                try:
                    return float(first[0])
                except Exception:
                    return 0.0
            if isinstance(first, dict):
                try:
                    return float(first.get("price", 0.0))
                except Exception:
                    return 0.0

        lay_ladder = data.get("lay_ladder", [])
        if lay_ladder and isinstance(lay_ladder, list):
            first = lay_ladder[0]
            if isinstance(first, dict):
                try:
                    return float(first.get("price", 0.0))
                except Exception:
                    return 0.0

        return 0.0

    def _build_ui(self):
        runner_name = self.selection_data.get("runnerName", "Unknown")

        self.header = ctk.CTkLabel(
            self,
            text=runner_name,
            font=("Segoe UI", 12, "bold"),
            text_color=COLORS["text_primary"],
        )
        self.header.pack(pady=(0, 5))

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill=tk.X)

        back_price = self._extract_back_price(self.selection_data)
        lay_price = self._extract_lay_price(self.selection_data)

        back_text = f"{back_price:.2f}" if back_price > 0 else "-"
        lay_text = f"{lay_price:.2f}" if lay_price > 0 else "-"

        self.btn_back = ctk.CTkButton(
            self.grid_frame,
            text=back_text,
            width=60,
            fg_color=COLORS["back"],
            hover_color=COLORS["back_hover"],
            text_color="#000000",
            command=lambda: self._on_price_clicked("BACK", back_price),
        )
        self.btn_back.pack(side=tk.LEFT, padx=2)

        self.btn_lay = ctk.CTkButton(
            self.grid_frame,
            text=lay_text,
            width=60,
            fg_color=COLORS["lay"],
            hover_color=COLORS["lay_hover"],
            text_color="#000000",
            command=lambda: self._on_price_clicked("LAY", lay_price),
        )
        self.btn_lay.pack(side=tk.LEFT, padx=2)

    def _get_current_stake(self):
        try:
            if hasattr(self.app, "stake_var"):
                return max(1.0, float(self.app.stake_var.get().replace(",", ".")))
        except Exception:
            pass
        return 1.0

    def _on_price_clicked(self, side, price):
        if price <= 0:
            messagebox.showwarning("Attenzione", "Quota non valida o mercato sospeso.")
            return

        stake = self._get_current_stake()

        mode_str = "[SIMULAZIONE] " if getattr(self.app, "simulation_mode", False) else ""
        msg = (
            f"{mode_str}Confermi la scommessa rapida?\n\n"
            f"Runner: {self.selection_data.get('runnerName', 'Unknown')}\n"
            f"Tipo: {side}\n"
            f"Quota: {price:.2f}\n"
            f"Stake: {stake:.2f} €"
        )

        if not messagebox.askyesno("Quick Bet", msg):
            return

        payload = {
            "market_id": str(self.market_data.get("marketId", "")),
            "market_type": str(self.market_data.get("marketType", "MATCH_ODDS")),
            "event_name": str(self.market_data.get("eventName", "")),
            "market_name": str(self.market_data.get("marketName", "")),
            "selection_id": self.selection_data.get("selectionId"),
            "runner_name": self.selection_data.get("runnerName", ""),
            "bet_type": side,
            "price": float(price),
            "stake": float(stake),
            "simulation_mode": bool(getattr(self.app, "simulation_mode", False)),
            "source": "UI_MINI_LADDER",
        }

        self.bus.publish("REQ_QUICK_BET", payload)

    def update_prices(self, new_back=None, new_lay=None):
        """
        Aggiorna la vista se cambiano le quote dal websocket/polling.
        Se un valore è None, prova a rileggerlo dal selection_data corrente.
        """
        if new_back is None:
            new_back = self._extract_back_price(self.selection_data)
        if new_lay is None:
            new_lay = self._extract_lay_price(self.selection_data)

        try:
            self.selection_data["backPrice"] = float(new_back) if new_back else 0.0
        except Exception:
            self.selection_data["backPrice"] = 0.0

        try:
            self.selection_data["layPrice"] = float(new_lay) if new_lay else 0.0
        except Exception:
            self.selection_data["layPrice"] = 0.0

        if self.btn_back:
            if new_back and float(new_back) > 0:
                self.btn_back.configure(
                    text=f"{float(new_back):.2f}",
                    command=lambda: self._on_price_clicked("BACK", float(new_back)),
                )
            else:
                self.btn_back.configure(text="-", command=lambda: None)

        if self.btn_lay:
            if new_lay and float(new_lay) > 0:
                self.btn_lay.configure(
                    text=f"{float(new_lay):.2f}",
                    command=lambda: self._on_price_clicked("LAY", float(new_lay)),
                )
            else:
                self.btn_lay.configure(text="-", command=lambda: None)
