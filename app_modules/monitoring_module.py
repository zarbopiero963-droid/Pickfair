import logging
import tkinter as tk
from tkinter import messagebox

from theme import COLORS

logger = logging.getLogger("MonitoringModule")


class MonitoringModule:

    # ==========================================
    # DASHBOARD STORICO
    # ==========================================
    def _refresh_dashboard_tab(self):
        if not hasattr(self, "db"):
            return

        today_pl = self.db.get_today_profit_loss()
        active_count = self.db.get_active_bets_count()

        if hasattr(self, "dash_pl_label") and self.dash_pl_label.winfo_exists():
            color = COLORS["success"] if today_pl >= 0 else COLORS["loss"]
            sign = "+" if today_pl > 0 else ""
            self.dash_pl_label.configure(
                text=f"{sign}{today_pl:.2f} €",
                text_color=color
            )

        if hasattr(self, "dash_active_label") and self.dash_active_label.winfo_exists():
            self.dash_active_label.configure(text=str(active_count))

        self._update_recent_bets_tree()

    def _update_recent_bets_tree(self):
        if not hasattr(self, "dash_history_tree") or not self.dash_history_tree.winfo_exists():
            return

        self.dash_history_tree.delete(*self.dash_history_tree.get_children())
        recent_bets = self.db.get_recent_bets(limit=20)

        for bet in recent_bets:
            dt = str(bet.get("placed_at", ""))[:16]
            market = bet.get("market_name", "Ignoto")
            bet_type = bet.get("bet_type", "-")
            stake = f"{float(bet.get('total_stake', 0) or 0):.2f}"
            pl = float(bet.get("potential_profit") or 0.0)
            pl_str = f"+{pl:.2f}" if pl > 0 else f"{pl:.2f}"
            status = bet.get("status", "UNKNOWN")

            self.dash_history_tree.insert(
                "",
                tk.END,
                values=(dt, market, bet_type, stake, pl_str, status)
            )

    # ==========================================
    # SCOMMESSE PIAZZATE (MERCATO CORRENTE)
    # ==========================================
    def _update_placed_bets(self):
        """Popola la UI leggendo dal Client Betfair o dal DB in caso di simulazione."""
        if not getattr(self, "current_market", None):
            return

        if hasattr(self, "placed_bets_tree") and self.placed_bets_tree.winfo_exists():
            self.placed_bets_tree.delete(*self.placed_bets_tree.get_children())

        if getattr(self, "simulation_mode", False):
            sim_bets = self.db.get_simulation_bets(limit=50)
            current_market_id = str(self.current_market.get("marketId", ""))

            for bet in sim_bets:
                if str(bet.get("market_id", "")) != current_market_id:
                    continue

                dt = str(bet.get("placed_at", ""))[:16]
                sel_name = bet.get("selection_name", "")
                side = bet.get("side", "")
                price = f"{float(bet.get('price', 0) or 0):.2f}"
                stake = f"{float(bet.get('stake', 0) or 0):.2f}"
                status = bet.get("status", "MATCHED")

                self.placed_bets_tree.insert(
                    "",
                    tk.END,
                    values=(dt, sel_name, side, price, stake, status)
                )
            return

        if not getattr(self, "client", None):
            return

        def fetch():
            try:
                orders = self.client.get_current_orders(
                    market_ids=[self.current_market["marketId"]]
                )
                self.uiq.post(self._render_placed_bets, orders)
            except Exception as e:
                logger.error(f"Errore recupero current_orders: {e}")

        self.executor.submit("fetch_orders", fetch)

    def _render_placed_bets(self, orders):
        if not hasattr(self, "placed_bets_tree") or not self.placed_bets_tree.winfo_exists():
            return

        self.placed_bets_tree.delete(*self.placed_bets_tree.get_children())

        current_orders = orders.get("currentOrders", []) if orders else []
        if not current_orders:
            return

        for order in current_orders:
            sel_id = str(order.get("selectionId", ""))
            sel_name = sel_id

            if getattr(self, "current_market", None):
                for runner in self.current_market.get("runners", []):
                    if str(runner.get("selectionId")) == sel_id:
                        sel_name = runner.get("runnerName", sel_id)
                        break

            side = order.get("side", "")
            price_size = order.get("priceSize", {}) or {}
            price = f"{float(price_size.get('price', 0) or 0):.2f}"
            stake = f"{float(price_size.get('size', 0) or 0):.2f}"

            raw_status = order.get("status", "UNKNOWN")
            matched = float(order.get("sizeMatched", 0) or 0)

            if raw_status == "EXECUTION_COMPLETE":
                status = "MATCHED"
            elif raw_status == "EXECUTABLE":
                status = "PARTIALLY_MATCHED" if matched > 0 else "UNMATCHED"
            else:
                status = raw_status

            self.placed_bets_tree.insert(
                "",
                tk.END,
                values=("Live", sel_name, side, price, stake, status)
            )

    # ==========================================
    # MONITORAGGIO CASHOUT
    # ==========================================
    def _start_market_live_tracking(self):
        def update():
            if not getattr(self, "market_live_tracking_var", None) or not self.market_live_tracking_var.get():
                return

            self._update_market_cashout_positions()
            self.market_live_tracking_id = self.root.after(15000, update)

        self._update_market_cashout_positions()
        self.market_live_tracking_id = self.root.after(15000, update)

        if hasattr(self, "market_live_status") and self.market_live_status.winfo_exists():
            self.market_live_status.configure(
                text="LIVE",
                text_color=COLORS["success"]
            )

    def _stop_market_live_tracking(self):
        if hasattr(self, "market_live_tracking_id") and self.market_live_tracking_id:
            try:
                self.root.after_cancel(self.market_live_tracking_id)
            except Exception:
                pass
            self.market_live_tracking_id = None

        if hasattr(self, "market_live_status") and self.market_live_status.winfo_exists():
            self.market_live_status.configure(
                text="STOP",
                text_color=COLORS["text_secondary"]
            )

    def _update_market_cashout_positions(self):
        if getattr(self, "simulation_mode", False):
            return
        if not getattr(self, "client", None):
            return
        if not getattr(self, "current_market", None):
            return

        def fetch():
            try:
                orders = self.client.get_current_orders(
                    market_ids=[self.current_market["marketId"]]
                )
                current_orders = orders.get("currentOrders", []) if orders else []
                positions = self._calculate_positions(current_orders)
                self.uiq.post(self._render_cashout_positions, positions)
            except Exception as e:
                logger.error(f"Errore calcolo posizioni cashout: {e}")

        self.executor.submit("fetch_cashout", fetch)

    def _calculate_positions(self, orders):
        positions = {}

        for order in orders:
            raw_status = order.get("status")
            matched_size = float(order.get("sizeMatched", 0) or 0)

            if raw_status == "EXECUTION_COMPLETE":
                pass
            elif raw_status == "EXECUTABLE" and matched_size > 0:
                pass
            else:
                continue

            sel_id = str(order.get("selectionId", ""))
            if not sel_id:
                continue

            if sel_id not in positions:
                positions[sel_id] = {
                    "selection_id": sel_id,
                    "bets": [],
                    "total_stake": 0.0,
                    "avg_price": 0.0,
                    "side": order.get("side", ""),
                }

            price_size = order.get("priceSize", {}) or {}
            price = float(order.get("averagePriceMatched") or price_size.get("price", 0) or 0)
            size = matched_size

            if size <= 0:
                continue

            positions[sel_id]["bets"].append(order)

            old_total = positions[sel_id]["total_stake"]
            new_total = old_total + size

            if new_total > 0:
                positions[sel_id]["avg_price"] = (
                    (positions[sel_id]["avg_price"] * old_total) + (price * size)
                ) / new_total

            positions[sel_id]["total_stake"] = new_total

        return positions

    def _render_cashout_positions(self, positions):
        if not hasattr(self, "market_cashout_tree") or not self.market_cashout_tree.winfo_exists():
            return

        self.market_cashout_tree.delete(*self.market_cashout_tree.get_children())
        self.market_cashout_positions = {}

        for sel_id, pos in positions.items():
            sel_name = sel_id
            current_back = 0.0
            current_lay = 0.0

            if getattr(self, "current_market", None):
                for runner in self.current_market.get("runners", []):
                    if str(runner.get("selectionId")) == sel_id:
                        sel_name = runner.get("runnerName", sel_id)
                        current_back = float(runner.get("backPrice", 0) or 0)
                        current_lay = float(runner.get("layPrice", 0) or 0)
                        break

            orig_side = pos["side"]
            avg_price = float(pos["avg_price"] or 0)
            stake = float(pos["total_stake"] or 0)

            cashout_side = "LAY" if orig_side == "BACK" else "BACK"
            current_price = current_back if cashout_side == "BACK" else current_lay

            green_up = 0.0
            cashout_stake = 0.0

            if current_price > 0 and stake > 0 and avg_price > 0:
                if orig_side == "BACK":
                    cashout_stake = (stake * avg_price) / current_price
                    green_up = cashout_stake - stake
                else:
                    cashout_stake = (stake * avg_price) / current_price
                    green_up = stake - cashout_stake

            pos["cashout_info"] = {
                "cashout_side": cashout_side,
                "cashout_stake": cashout_stake,
                "current_price": current_price,
                "green_up": green_up,
            }

            self.market_cashout_positions[sel_id] = pos

            pl_str = f"+{green_up:.2f}" if green_up > 0 else f"{green_up:.2f}"
            self.market_cashout_tree.insert(
                "",
                tk.END,
                iid=sel_id,
                values=(
                    sel_name,
                    orig_side,
                    f"{stake:.2f}",
                    f"{avg_price:.2f}",
                    pl_str,
                )
            )

    # ==========================================
    # ESECUZIONE CASHOUT VIA OMS
    # ==========================================
    def _execute_cashout(self):
        """Delega l'intento di cashout al RiskMiddleware/OMS."""
        if not hasattr(self, "market_cashout_tree"):
            return

        selected = self.market_cashout_tree.selection()
        if not selected:
            messagebox.showwarning(
                "Attenzione",
                "Seleziona una posizione per il Cashout."
            )
            return

        sel_id = selected[0]
        pos = getattr(self, "market_cashout_positions", {}).get(sel_id)
        if not pos:
            return

        info = pos.get("cashout_info")
        if not info or float(info.get("current_price", 0) or 0) <= 0:
            messagebox.showerror(
                "Errore",
                "Quota di uscita non disponibile o mercato sospeso."
            )
            return

        msg = (
            f"Confermi l'intento di Cashout all'OMS?\n\n"
            f"Tipo Ordine: {info['cashout_side']}\n"
            f"Quota: {float(info['current_price']):.2f}\n"
            f"Stake Richiesto: {float(info['cashout_stake']):.2f} €\n"
            f"P&L Stimato: {float(info['green_up']):.2f} €"
        )
        if not messagebox.askyesno("Conferma Cashout", msg):
            return

        payload = {
            "market_id": self.current_market["marketId"],
            "selection_id": sel_id,
            "side": info["cashout_side"],
            "stake": float(info["cashout_stake"]),
            "price": float(info["current_price"]),
            "green_up": float(info["green_up"]),
            "original_pos": pos,
        }

        logger.info(
            f"Invio intento Cashout all'EventBus (REQ_EXECUTE_CASHOUT): {payload}"
        )
        self.bus.publish("REQ_EXECUTE_CASHOUT", payload)

    # ==========================================
    # CALLBACKS DA OMS
    # ==========================================
    def _on_cashout_success(self, data):
        matched = float(data.get("matched", 0) or 0)
        green_up = float(data.get("green_up", 0) or 0)

        msg = "L'OMS ha elaborato il cashout!"
        if matched > 0:
            msg += f"\n\nImporto Abbinato: {matched:.2f} €"
        msg += f"\nP&L Stimato: {green_up:.2f} €"

        messagebox.showinfo("Cashout Eseguito", msg)

        self._update_market_cashout_positions()
        self._update_placed_bets()
        if hasattr(self, "_update_balance"):
            self._update_balance()

    def _on_cashout_failed(self, error):
        messagebox.showerror(
            "Cashout Fallito",
            f"L'OMS ha riscontrato un errore:\n{error}"
        )

