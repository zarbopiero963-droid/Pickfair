import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from theme import COLORS, FONTS


class MonitoringModule:
    def _update_placed_bets(self):
        """Update placed bets list for current market."""
        if not self.client or not getattr(self, "current_market", None):
            return

        market_id = self.current_market.get("marketId")
        if not market_id:
            return

        runner_names = {}
        for runner in self.current_market.get("runners", []):
            runner_names[runner["selectionId"]] = runner["runnerName"]

        def fetch_bets():
            try:
                orders = self.client.get_current_orders()
                matched = orders.get("matched", [])
                market_orders = [o for o in matched if o.get("marketId") == market_id]
                self.uiq.post(self._display_placed_bets, market_orders, runner_names)
            except Exception as e:
                print(f"Error fetching placed bets: {e}")

        self.executor.submit("fetch_placed_bets", fetch_bets)

    def _display_placed_bets(self, orders, runner_names):
        """Display placed bets in treeview using TreeManager."""
        bets_data = []
        for order in orders:
            selection_id = order.get("selectionId")
            side = order.get("side", "BACK")
            price = order.get("price", 0)
            stake = order.get("sizeMatched", 0)
            bet_id = order.get("betId")

            runner_name = runner_names.get(selection_id, f"ID:{selection_id}")
            if len(runner_name) > 15:
                runner_name = runner_name[:15] + "..."

            tag = "back" if side == "BACK" else "lay"

            bets_data.append(
                {
                    "id": bet_id,
                    "values": (runner_name, side[:1], f"{price:.2f}", f"{stake:.2f}"),
                    "tags": (tag,),
                }
            )

        self.tm_placed_bets.update_flat(
            data=bets_data,
            id_getter=lambda b: str(b["id"]),
            values_getter=lambda b: b["values"],
            tags_getter=lambda b: b["tags"],
        )

    def _update_market_cashout_positions(self):
        """Update cashout positions for current market."""
        if getattr(self, "market_cashout_fetch_in_progress", False):
            return

        if not self.client or not getattr(self, "current_market", None):
            if (
                hasattr(self, "market_cashout_btn")
                and self.market_cashout_btn.winfo_exists()
            ):
                self.market_cashout_btn.configure(state=tk.DISABLED)
            return

        market_id = self.current_market.get("marketId")
        if not market_id:
            return

        self.market_cashout_fetch_in_progress = True
        self.market_cashout_fetch_cancelled = False

        current_market_id = market_id

        def fetch_positions():
            try:
                if getattr(self, "market_cashout_fetch_cancelled", False):
                    self.market_cashout_fetch_in_progress = False
                    return

                orders = self.client.get_current_orders()
                matched = orders.get("matched", [])

                if getattr(self, "market_cashout_fetch_cancelled", False):
                    self.market_cashout_fetch_in_progress = False
                    return

                market_orders = [
                    o for o in matched if o.get("marketId") == current_market_id
                ]

                positions = []
                for order in market_orders:
                    if getattr(self, "market_cashout_fetch_cancelled", False):
                        self.market_cashout_fetch_in_progress = False
                        return

                    selection_id = order.get("selectionId")
                    side = order.get("side")
                    price = order.get("price", 0)
                    stake = order.get("sizeMatched", 0)

                    if stake > 0:
                        try:
                            cashout_info = self.client.calculate_cashout(
                                current_market_id, selection_id, side, stake, price
                            )
                            green_up = cashout_info.get("green_up", 0)
                        except:
                            cashout_info = None
                            green_up = 0

                        runner_name = str(selection_id)
                        if (
                            self.current_market
                            and self.current_market.get("marketId") == current_market_id
                        ):
                            for r in self.current_market.get("runners", []):
                                if str(r.get("selectionId")) == str(selection_id):
                                    runner_name = r.get("runnerName", runner_name)[:15]
                                    break

                        positions.append(
                            {
                                "bet_id": order.get("betId"),
                                "selection_id": selection_id,
                                "runner_name": runner_name,
                                "side": side,
                                "price": price,
                                "stake": stake,
                                "green_up": green_up,
                                "cashout_info": cashout_info,
                            }
                        )

                def update_ui():
                    self.market_cashout_fetch_in_progress = False
                    if not getattr(self, "market_cashout_fetch_cancelled", False):
                        if (
                            getattr(self, "current_market", None)
                            and self.current_market.get("marketId") == current_market_id
                        ):
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
            bet_id = pos["bet_id"]
            green_up = pos["green_up"]
            pl_tag = "profit" if green_up > 0 else "loss"

            self.market_cashout_positions[str(bet_id)] = pos

            cashout_data.append(
                {
                    "id": bet_id,
                    "values": (pos["runner_name"], pos["side"], f"{green_up:+.2f}"),
                    "tags": (pl_tag,),
                }
            )

        self.tm_cashout.update_flat(
            data=cashout_data,
            id_getter=lambda c: str(c["id"]),
            values_getter=lambda c: c["values"],
            tags_getter=lambda c: c["tags"],
        )

        if (
            hasattr(self, "market_cashout_btn")
            and self.market_cashout_btn.winfo_exists()
        ):
            if positions:
                self.market_cashout_btn.configure(state=tk.NORMAL)
            else:
                self.market_cashout_btn.configure(state=tk.DISABLED)

    def _toggle_market_live_tracking(self):
        if self.market_live_tracking_var.get():
            self._start_market_live_tracking()
        else:
            self._stop_market_live_tracking()

    def _start_market_live_tracking(self):
        def update():
            if not self.market_live_tracking_var.get():
                return
            self._update_market_cashout_positions()
            self.market_live_tracking_id = self.root.after(5000, update)

        self._update_market_cashout_positions()
        self.market_live_tracking_id = self.root.after(5000, update)
        if (
            hasattr(self, "market_live_status")
            and self.market_live_status.winfo_exists()
        ):
            self.market_live_status.configure(text="LIVE", text_color=COLORS["success"])

    def _stop_market_live_tracking(self):
        if getattr(self, "market_live_tracking_id", None):
            self.root.after_cancel(self.market_live_tracking_id)
            self.market_live_tracking_id = None
        self.market_cashout_fetch_cancelled = True
        if (
            hasattr(self, "market_live_status")
            and self.market_live_status.winfo_exists()
        ):
            self.market_live_status.configure(
                text="", text_color=COLORS["text_secondary"]
            )

    def _do_single_cashout(self, event):
        item = self.market_cashout_tree.identify_row(event.y)
        if item:
            self.market_cashout_tree.selection_set(item)
            self._do_market_cashout()

    def _refresh_dashboard_tab(self):
        """Refresh dashboard tab data."""
        if not self.client:
            if (
                hasattr(self, "dashboard_not_connected")
                and self.dashboard_not_connected.winfo_exists()
            ):
                self.dashboard_not_connected.configure(
                    text="Connettiti a Betfair per vedere i dati"
                )
            return

        if (
            hasattr(self, "dashboard_not_connected")
            and self.dashboard_not_connected.winfo_exists()
        ):
            self.dashboard_not_connected.configure(text="")

        def create_stat_card(parent, title, value, subtitle, col):
            import customtkinter as ctk

            card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=8)
            card.grid(row=0, column=col, padx=5, sticky="nsew")
            ctk.CTkLabel(
                card,
                text=title,
                font=("Segoe UI", 9),
                text_color=COLORS["text_secondary"],
            ).pack(pady=(10, 2))
            ctk.CTkLabel(
                card, text=value, font=FONTS["title"], text_color=COLORS["text_primary"]
            ).pack()
            ctk.CTkLabel(
                card,
                text=subtitle,
                font=("Segoe UI", 8),
                text_color=COLORS["text_tertiary"],
            ).pack(pady=(2, 10))
            return card

        def fetch_data():
            try:
                funds = self.client.get_account_funds()
                self.account_data = funds
                daily_pl = self.db.get_today_profit_loss()
                try:
                    orders = self.client.get_current_orders()
                    active_count = len(
                        [
                            o
                            for o in orders.get("matched", [])
                            if o.get("sizeMatched", 0) > 0
                        ]
                    )
                except:
                    active_count = self.db.get_active_bets_count()

                try:
                    settled_bets = self.client.get_settled_bets(days=7)
                except:
                    settled_bets = []

                self.uiq.post(
                    update_ui, funds, daily_pl, active_count, orders, settled_bets
                )
            except Exception as e:
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", err_msg)

        def update_ui(funds, daily_pl, active_count, orders, settled_bets=None):
            if (
                not hasattr(self, "dashboard_stats_frame")
                or not self.dashboard_stats_frame.winfo_exists()
            ):
                return
            for widget in self.dashboard_stats_frame.winfo_children():
                widget.destroy()

            create_stat_card(
                self.dashboard_stats_frame,
                "Saldo Disponibile",
                f"{funds.get('available', 0):.2f} EUR",
                "Fondi disponibili",
                0,
            )
            create_stat_card(
                self.dashboard_stats_frame,
                "Esposizione",
                f"{abs(funds.get('exposure', 0)):.2f} EUR",
                "Responsabilita corrente",
                1,
            )
            pl_text = f"+{daily_pl:.2f}" if daily_pl >= 0 else f"{daily_pl:.2f}"
            create_stat_card(
                self.dashboard_stats_frame,
                "P/L Oggi",
                f"{pl_text} EUR",
                "Profitto/Perdita giornaliero",
                2,
            )
            create_stat_card(
                self.dashboard_stats_frame,
                "Scommesse Attive",
                str(active_count),
                "In attesa di risultato",
                3,
            )

            for i in range(4):
                self.dashboard_stats_frame.columnconfigure(i, weight=1)

            for widget in self.dashboard_recent_frame.winfo_children():
                widget.destroy()
            self._create_settled_bets_list(
                self.dashboard_recent_frame, settled_bets or []
            )

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

    def _toggle_auto_refresh(self):
        if self.auto_refresh_var.get():
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    def _start_auto_refresh(self):
        if not self.client:
            self.auto_refresh_var.set(False)
            return

        self._stop_auto_refresh()
        interval_ms = int(self.auto_refresh_interval_var.get()) * 1000

        def do_refresh():
            if self.client and self.auto_refresh_var.get():
                self._load_events()
                self._update_balance()
                now = datetime.now().strftime("%H:%M:%S")
                if (
                    hasattr(self, "auto_refresh_status")
                    and self.auto_refresh_status.winfo_exists()
                ):
                    self.auto_refresh_status.configure(text=f"Ultimo: {now}")
                self.auto_refresh_id = self.root.after(interval_ms, do_refresh)

        self.auto_refresh_id = self.root.after(interval_ms, do_refresh)
        if (
            hasattr(self, "auto_refresh_status")
            and self.auto_refresh_status.winfo_exists()
        ):
            self.auto_refresh_status.configure(text="Attivo")

    def _stop_auto_refresh(self):
        if getattr(self, "auto_refresh_id", None):
            self.root.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None
        if (
            hasattr(self, "auto_refresh_status")
            and self.auto_refresh_status.winfo_exists()
        ):
            self.auto_refresh_status.configure(text="")

    def _on_auto_refresh_interval_change(self, event=None):
        if self.auto_refresh_var.get():
            self._start_auto_refresh()

    # --- ADAPTER LAYER (Invia comandi al TradingEngine tramite EventBus) ---
    def _do_market_cashout(self):
        selected = self.market_cashout_tree.selection()
        if not selected:
            return messagebox.showwarning("Attenzione", "Seleziona una posizione")

        for bet_id in selected:
            pos = self.market_cashout_positions.get(bet_id)
            if not pos or not pos.get("cashout_info"):
                continue

            info = pos["cashout_info"]
            if (
                not getattr(self, "auto_cashout_var", None)
                or not self.auto_cashout_var.get()
            ):
                if not messagebox.askyesno(
                    "Conferma Cashout",
                    f"Eseguire cashout?\nTipo: {info['cashout_side']} @ {info['current_price']:.2f}\nStake: {info['cashout_stake']:.2f}\nProfitto: {info['green_up']:+.2f}",
                ):
                    continue

            # Invia comando al TradingEngine
            self.bus.publish(
                "CMD_EXECUTE_CASHOUT",
                {
                    "market_id": self.current_market["marketId"],
                    "selection_id": pos["selection_id"],
                    "side": info["cashout_side"],
                    "stake": info["cashout_stake"],
                    "price": info["current_price"],
                    "bet_id": bet_id,
                    "green_up": info["green_up"],
                    "original_pos": pos,
                },
            )

    def _on_cashout_success(self, data):
        messagebox.showinfo(
            "Successo", f"Cashout eseguito!\nProfitto bloccato: {data['green_up']:+.2f}"
        )
        self._update_market_cashout_positions()
        self._update_balance()

    def _on_cashout_failed(self, err):
        messagebox.showerror("Errore Cashout", err)
