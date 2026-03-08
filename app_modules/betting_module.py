import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from betfair_client import BetfairClient
from dutching import calculate_dutching_stakes, format_currency, validate_selections
from dutching_ui import open_dutching_window
from theme import COLORS

class BettingModule:
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

    def _on_goal_reopen(self, match_id):
        import logging
        logging.getLogger("PickfairApp").info(f"REOPEN positions match={match_id}")

    def _toggle_connection(self):
        if self.client:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        settings = self.db.get_settings()
        if not all([settings.get("username"), settings.get("app_key"), settings.get("certificate"), settings.get("private_key")]):
            messagebox.showerror("Errore", "Configura prima le credenziali dal menu File")
            return

        from tkinter import ttk
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

        saved_password = settings.get("password", "")
        pwd_var = tk.StringVar(value=saved_password or "")
        pwd_entry = ttk.Entry(frame, textvariable=pwd_var, show="*")
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
            self.status_label.configure(text="Connessione in corso...", text_color=COLORS["text_secondary"])
            self.connect_btn.configure(state=tk.DISABLED)

            def login_thread():
                try:
                    self.client = BetfairClient(
                        settings["username"],
                        settings["app_key"],
                        settings["certificate"],
                        settings["private_key"],
                    )
                    result = self.client.login(password)
                    self.db.save_session(result["session_token"], result["expiry"])
                    self.uiq.post(self._on_connected)
                except Exception as e:
                    self.uiq.post(self._on_connection_error, str(e))

            self.executor.submit("login_task", login_thread)

        pwd_entry.bind("<Return>", lambda e: do_login())
        ttk.Button(frame, text="Connetti", command=do_login).pack(pady=10)

    def _on_connected(self):
        self.status_label.configure(text="Connesso a Betfair Italia", text_color=COLORS["success"])
        self.connect_btn.configure(text="Disconnetti", state=tk.NORMAL)
        self.refresh_btn.configure(state=tk.NORMAL)

        self._update_balance()
        self._load_events()

        self.auto_refresh_var.set(True)
        self._start_auto_refresh()

        self._start_session_keepalive()
        self._refresh_dashboard_tab()

        self.bus.publish("CLIENT_CONNECTED", None)

    def _start_session_keepalive(self):
        self.keepalive_id = None
        def keepalive():
            if self.client:
                try:
                    self.client.get_account_balance()
                except Exception:
                    self._try_silent_relogin()
            if self.client:
                self.keepalive_id = self.root.after(600000, keepalive)
        self.keepalive_id = self.root.after(600000, keepalive)

    def _stop_session_keepalive(self):
        if hasattr(self, "keepalive_id") and self.keepalive_id:
            self.root.after_cancel(self.keepalive_id)
            self.keepalive_id = None

    def _try_silent_relogin(self):
        settings = self.db.get_settings()
        password = settings.get("password")
        if password and self.client:
            try:
                result = self.client.login(password)
                self.db.save_session(result["session_token"], result["expiry"])
            except Exception:
                self.uiq.post(messagebox.showwarning, "Sessione Scaduta", "La sessione è scaduta. Riconnettiti manualmente.")

    def _on_connection_error(self, error):
        self.status_label.configure(text=f"Errore: {error}", text_color=COLORS["error"])
        self.connect_btn.configure(text="Connetti", state=tk.NORMAL)
        self.client = None
        messagebox.showerror("Errore Connessione", error)

    def _disconnect(self):
        self._stop_auto_refresh()
        self._stop_session_keepalive()
        self.auto_refresh_var.set(False)

        if self.client:
            self.client.logout()
            self.client = None

        self.db.clear_session()
        self.status_label.configure(text="Non connesso", text_color=COLORS["error"])
        self.stream_label.configure(text="")
        self.connect_btn.configure(text="Connetti")
        self.refresh_btn.configure(state=tk.DISABLED)
        self.balance_label.configure(text="")
        self.streaming_active = False
        self.stream_var.set(False)

        self.events_tree.delete(*self.events_tree.get_children())
        self.runners_tree.delete(*self.runners_tree.get_children())
        self.market_combo["values"] = []
        self._clear_selections()

    def _update_balance(self):
        def fetch():
            try:
                funds = self.client.get_account_funds()
                self.uiq.post(self.balance_label.configure, text=f"Saldo: {format_currency(funds['available'])}")
            except Exception:
                pass
        self.executor.submit("fetch_balance", fetch)

    def _load_events(self):
        def fetch():
            try:
                events = self.client.get_football_events()
                self.uiq.post(self._display_events, events)
            except Exception as e:
                self.uiq.post(messagebox.showerror, "Errore", f"Errore caricamento partite: {str(e)}")
        self.executor.submit("fetch_events", fetch)

    def _display_events(self, events):
        self.all_events = events
        self._populate_events_tree()

    def _populate_events_tree(self):
        search = self.search_var.get().lower()
        filtered_events = []
        if search:
            for event in self.all_events:
                if search in event["name"].lower():
                    filtered_events.append(event)
        else:
            filtered_events = self.all_events

        self.tm_events.update_hierarchical(
            data=filtered_events,
            parent_getter=lambda e: f"country_{e.get('countryCode', 'XX') or 'XX'}",
            id_getter=lambda e: e["id"],
            text_getter=lambda e: e.get("countryCode", "XX") or "XX",
            values_getter=lambda e: (e["name"], self._format_event_date(e)),
        )

    def _format_event_date(self, event):
        if event.get("inPlay"):
            return "LIVE"
        if event.get("openDate"):
            try:
                dt = datetime.fromisoformat(event["openDate"].replace("Z", "+00:00"))
                return dt.strftime("%d/%m %H:%M")
            except:
                return event["openDate"][:16]
        return ""

    def _filter_events(self, *args):
        self._populate_events_tree()

    def _refresh_data(self):
        self._update_balance()
        self._load_events()
        if self.current_event:
            self._load_available_markets(self.current_event["id"])

    def _on_event_selected(self, event):
        selection = self.events_tree.selection()
        if not selection:
            return
        event_id = selection[0]
        if event_id.startswith("country_"):
            return

        for evt in self.all_events:
            if evt["id"] == event_id:
                self.current_event = evt
                self.event_name_label.configure(text=evt["name"])
                break
        else:
            return

        self._stop_streaming()
        self._clear_selections()
        self._load_available_markets(event_id)

    def _load_available_markets(self, event_id):
        self.runners_tree.delete(*self.runners_tree.get_children())
        self.market_combo["values"] = []

        def fetch():
            try:
                markets = self.client.get_available_markets(event_id)
                self.uiq.post(self._display_available_markets, markets)
            except Exception as e:
                self.uiq.post(messagebox.showerror, "Errore", f"Errore caricamento mercati: {str(e)}")
        self.executor.submit("fetch_markets", fetch)

    def _display_available_markets(self, markets):
        self.available_markets = markets
        if not markets:
            self.market_combo["values"] = ["Nessun mercato disponibile"]
            return

        display_names = []
        for m in markets:
            name = m.get("displayName") or m.get("marketName", "Sconosciuto")
            if m.get("inPlay"):
                name = f"[LIVE] {name}"
            display_names.append(name)

        self.market_combo["values"] = display_names
        if display_names:
            self.market_combo.current(0)
            self._on_market_type_selected(None)

    def _on_market_type_selected(self, event):
        selection = self.market_combo.current()
        if selection < 0 or selection >= len(self.available_markets):
            return
        market = self.available_markets[selection]
        self._stop_streaming()
        self._clear_selections()
        self._load_market(market["marketId"])

    def _load_market(self, market_id):
        self.runners_tree.delete(*self.runners_tree.get_children())
        def fetch():
            try:
                market = self.client.get_market_with_prices(market_id)
                self.uiq.post(self._display_market, market)
            except Exception as e:
                self.uiq.post(messagebox.showerror, "Errore", f"Mercato non disponibile: {str(e)}")
        self.executor.submit("fetch_market_prices", fetch)

    def _display_market(self, market):
        self.current_market = market
        self.market_status = market.get("status", "OPEN")
        is_inplay = market.get("inPlay", False)

        if self.market_status == "SUSPENDED":
            self.market_status_label.configure(text="SOSPESO", text_color=COLORS["loss"])
            self.dutch_modal_btn.configure(state=tk.DISABLED)
            self.place_btn.configure(state=tk.DISABLED)
        elif self.market_status == "CLOSED":
            self.market_status_label.configure(text="CHIUSO", text_color=COLORS["text_secondary"])
            self.dutch_modal_btn.configure(state=tk.DISABLED)
            self.place_btn.configure(state=tk.DISABLED)
        else:
            if is_inplay:
                self.market_status_label.configure(text="LIVE - APERTO", text_color=COLORS["success"])
            else:
                self.market_status_label.configure(text="APERTO", text_color=COLORS["success"])
            self.dutch_modal_btn.configure(state=tk.NORMAL)

        runners_data = []
        for runner in market["runners"]:
            back_price = f"{runner['backPrice']:.2f}" if runner.get("backPrice") else "-"
            lay_price = f"{runner['layPrice']:.2f}" if runner.get("layPrice") else "-"
            back_size = f"{runner['backSize']:.0f}" if runner.get("backSize") else "-"
            lay_size = f"{runner['laySize']:.0f}" if runner.get("laySize") else "-"
            sel_indicator = "X" if str(runner["selectionId"]) in self.selected_runners else ""

            runners_data.append({
                "id": runner["selectionId"],
                "values": (sel_indicator, runner["runnerName"], back_price, back_size, lay_price, lay_size),
                "tags": ("runner_row",)
            })

        self.tm_runners.update_flat(
            data=runners_data,
            id_getter=lambda r: str(r["id"]),
            values_getter=lambda r: r["values"],
            tags_getter=lambda r: r["tags"],
        )

        if self.market_status not in ("SUSPENDED", "CLOSED"):
            self.stream_var.set(True)
            self._start_streaming()

        self._update_placed_bets()
        self._update_market_cashout_positions()

        if self.market_live_tracking_var.get() and not getattr(self, "market_live_tracking_id", None):
            self._start_market_live_tracking()

    def _show_runner_context_menu(self, event):
        item = self.runners_tree.identify_row(event.y)
        if item:
            self.runners_tree.selection_set(item)
            self._context_menu_selection = item
            self.runner_context_menu.post(event.x_root, event.y_root)

    def _book_selected_runner(self):
        if not hasattr(self, "_context_menu_selection") or not self._context_menu_selection:
            return
        selection_id = self._context_menu_selection
        if not self.current_market:
            return
        for runner in self.current_market["runners"]:
            if str(runner["selectionId"]) == selection_id:
                current_price = runner.get("backPrice") or runner.get("layPrice") or 0
                if current_price > 0:
                    if hasattr(self, "_show_booking_dialog"):
                        self._show_booking_dialog(selection_id, runner["runnerName"], current_price, self.current_market["marketId"])
                break

    def _on_runner_clicked(self, event):
        item = self.runners_tree.identify_row(event.y)
        if not item: return
        column = self.runners_tree.identify_column(event.x)
        selection_id = item

        if column == "#3": return self._quick_bet(selection_id, "BACK")
        if column == "#5": return self._quick_bet(selection_id, "LAY")

        if selection_id in self.selected_runners:
            del self.selected_runners[selection_id]
            values = list(self.runners_tree.item(item)["values"])
            values[0] = ""
            self.runners_tree.item(item, values=values)
        else:
            if self.current_market:
                for runner in self.current_market["runners"]:
                    if str(runner["selectionId"]) == selection_id:
                        runner_data = runner.copy()
                        values = list(self.runners_tree.item(item)["values"])
                        try:
                            back_price = float(str(values[2]).replace(",", ".")) if values[2] and values[2] != "-" else 0
                            lay_price = float(str(values[4]).replace(",", ".")) if values[4] and values[4] != "-" else 0
                        except (ValueError, IndexError):
                            back_price = 0
                            lay_price = 0

                        runner_data["backPrice"] = back_price
                        runner_data["layPrice"] = lay_price
                        bet_type = self.bet_type_var.get()
                        runner_data["price"] = back_price if bet_type == "BACK" else lay_price

                        self.selected_runners[selection_id] = runner_data
                        values[0] = "X"
                        self.runners_tree.item(item, values=values)
                        break
        self._recalculate()

    def _quick_bet(self, selection_id, bet_type):
        if not self.client and not self.simulation_mode:
            return messagebox.showwarning("Attenzione", "Devi prima connetterti")
        if not self.current_market:
            return

        runner = next((r for r in self.current_market["runners"] if str(r["selectionId"]) == selection_id), None)
        if not runner: return

        values = list(self.runners_tree.item(selection_id)["values"])
        try:
            price = float(str(values[2]).replace(",", ".")) if bet_type == "BACK" and values[2] != "-" else float(str(values[4]).replace(",", ".")) if values[4] != "-" else 0
        except:
            price = 0

        if price <= 0: return messagebox.showwarning("Attenzione", "Quota non disponibile")

        try: stake = float(self.stake_var.get().replace(",", "."))
        except: stake = 1.0
        if stake < 1.0: stake = 1.0

        tipo_text = "Back (Punta)" if bet_type == "BACK" else "Lay (Banca)"
        mode_text = "[SIMULAZIONE] " if self.simulation_mode else ""

        if not messagebox.askyesno("Conferma Scommessa Rapida", f"{mode_text}Vuoi piazzare questa scommessa?\n\n{runner['runnerName']}\nTipo: {tipo_text}\nQuota: {price:.2f}\nStake: {stake:.2f} EUR"):
            return

        self.bus.publish("REQ_QUICK_BET", {
            "market_id": self.current_market["marketId"],
            "market_type": self.current_market.get("marketType", "MATCH_ODDS"),
            "event_name": getattr(self, "current_event", {}).get("name", ""),
            "market_name": self.current_market.get("marketName", ""),
            "selection_id": runner['selectionId'],
            "runner_name": runner['runnerName'],
            "bet_type": bet_type,
            "price": price,
            "stake": stake,
            "simulation_mode": self.simulation_mode,
        })

    def _set_bet_type(self, bet_type):
        self.bet_type_var.set(bet_type)
        if bet_type == "BACK":
            self.back_btn.configure(fg_color=COLORS["back"])
            self.lay_btn.configure(fg_color=COLORS["button_secondary"])
        else:
            self.back_btn.configure(fg_color=COLORS["button_secondary"])
            self.lay_btn.configure(fg_color=COLORS["lay"])
        self._recalculate()

    def _clear_selections(self):
        self.selected_runners = {}
        for item in self.runners_tree.get_children():
            values = list(self.runners_tree.item(item)["values"])
            values[0] = ""
            self.runners_tree.item(item, values=values)
        self.selections_text.configure(state=tk.NORMAL)
        self.selections_text.delete("1.0", tk.END)
        self.selections_text.configure(state=tk.DISABLED)
        self.profit_label.configure(text="Profitto: -")
        self.prob_label.configure(text="Probabilita Implicita: -")
        self.place_btn.configure(state=tk.DISABLED)
        self.calculated_results = None

    def _recalculate(self):
        if not self.selected_runners:
            self.selections_text.configure(state=tk.NORMAL)
            self.selections_text.delete("1.0", tk.END)
            self.selections_text.configure(state=tk.DISABLED)
            self.profit_label.configure(text="Profitto: -")
            self.prob_label.configure(text="Probabilita Implicita: -")
            self.place_btn.configure(state=tk.DISABLED)
            return

        self.selections_text.configure(state=tk.NORMAL)
        self.selections_text.delete("1.0", tk.END)
        try: total_stake = float(self.stake_var.get().replace(",", "."))
        except ValueError: total_stake = 10.0

        bet_type = self.bet_type_var.get()
        for sel_id, sel in self.selected_runners.items():
            sel["price"] = sel.get("backPrice", 0) if bet_type == "BACK" else sel.get("layPrice", 0)

        try:
            results, profit, implied_prob = calculate_dutching_stakes(list(self.selected_runners.values()), total_stake, bet_type)
            text_lines = []
            for r in results:
                text_lines.append(f"{r['runnerName']}")
                text_lines.append(f"  Quota: {r['price']:.2f}")
                text_lines.append(f"  Stake: {format_currency(r['stake'])}")
                if bet_type == "LAY":
                    text_lines.append(f"  Liability: {format_currency(r.get('liability', 0))}")
                    text_lines.append(f"  Se vince: {format_currency(r['profitIfWins'])}")
                else:
                    text_lines.append(f"  Profitto se vince: {format_currency(r['profitIfWins'])}")
                text_lines.append("")
            self.selections_text.insert("1.0", "\n".join(text_lines))
            if bet_type == "LAY" and results:
                self.profit_label.configure(text=f"Profitto Max: {format_currency(results[0].get('bestCase', profit))} | Rischio: {format_currency(results[0].get('worstCase', 0))}")
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
            self.selections_text.insert("1.0", f"Errore calcolo: {e}")
            self.profit_label.configure(text="Profitto: -")
            self.place_btn.configure(state=tk.DISABLED)
        self.selections_text.configure(state=tk.DISABLED)

    def _open_dutching_window(self):
        if not self.current_market: return messagebox.showwarning("Attenzione", "Seleziona prima un mercato.")
        if not self.client: return messagebox.showwarning("Attenzione", "Connettiti prima a Betfair.")
        runners = []
        for item in self.runners_tree.get_children():
            values = self.runners_tree.item(item, "values")
            sel_id = self.runners_tree.item(item, "tags")[0] if self.runners_tree.item(item, "tags") else None
            if sel_id:
                try: back_price = float(values[2]) if values[2] else 0
                except: back_price = 0
                runners.append({"selectionId": int(sel_id), "runnerName": values[1] if len(values) > 1 else "", "price": back_price})
        if not runners: return messagebox.showwarning("Attenzione", "Nessun runner disponibile.")

        market_data = {
            "marketId": self.current_market["marketId"],
            "marketName": self.current_market.get("marketName", ""),
            "eventName": self.current_event.get("name", "") if self.current_event else "",
            "startTime": self.current_event.get("openDate", "")[:16] if self.current_event else "",
            "status": self.market_status,
        }
        open_dutching_window(
            parent=self.root, market_data=market_data, runners=runners,
            on_submit=self._place_dutching_orders, on_refresh=getattr(self, "_refresh_prices", None),
        )

    def _place_dutching_orders(self, orders):
        if not orders: return
        if not self.current_market or not self.client: return messagebox.showerror("Errore", "Connessione o mercato non disponibile.")
        market_id = self.current_market["marketId"]
        if self.simulation_mode:
            for o in orders:
                self.db.add_simulated_bet(market_id=market_id, selection_id=o["selectionId"], runner_name=o["runnerName"], side=o["side"], price=o["price"], stake=o["size"])
            return messagebox.showinfo("Simulazione", f"Piazzati {len(orders)} ordini simulati.")
        try:
            instructions = [{"selectionId": o["selectionId"], "side": o["side"], "orderType": "LIMIT", "limitOrder": {"size": round(o["size"], 2), "price": o["price"], "persistenceType": "LAPSE"}} for o in orders]
            result = self.client.place_orders(market_id, instructions)
            if result and result.get("status") == "SUCCESS":
                messagebox.showinfo("Successo", f"Piazzati {len(orders)} ordini Dutching.")
                self._refresh_data()
            else:
                messagebox.showerror("Errore", f"Errore piazzamento: {result.get('errorCode', 'Errore sconosciuto') if result else 'Nessuna risposta'}")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {str(e)}")

    def _place_bets(self):
        if getattr(self, "_placing_in_progress", False) or not getattr(self, "calculated_results", None) or not self.current_market: return
        if self.market_status in ("SUSPENDED", "CLOSED"): return messagebox.showwarning("Attenzione", "Mercato sospeso o chiuso.")

        total_stake = sum(r["stake"] for r in self.calculated_results)
        if self.simulation_mode:
            sim_settings = self.db.get_simulation_settings()
            virtual_balance = sim_settings.get("virtual_balance", 0) if sim_settings else 0
            if total_stake > virtual_balance:
                return messagebox.showwarning("Saldo Insufficiente", f"Stake: {total_stake}\nSaldo: {virtual_balance}")
            if not messagebox.askyesno("Conferma Simulazione", f"Piazzare {len(self.calculated_results)} scommesse simulate?"): return
        else:
            if not messagebox.askyesno("Conferma", f"Piazzare {len(self.calculated_results)} scommesse?\nStake Totale: {total_stake}"): return

        self.place_btn.configure(state=tk.DISABLED)
        self._placing_in_progress = True

        self.bus.publish("REQ_PLACE_DUTCHING", {
            "market_id": self.current_market["marketId"],
            "market_type": self.current_market.get("marketType", "MATCH_ODDS"),
            "event_name": getattr(self, "current_event", {}).get("name", ""),
            "market_name": self.current_market.get("marketName", ""),
            "results": self.calculated_results,
            "bet_type": self.bet_type_var.get(),
            "total_stake": total_stake,
            "use_best_price": self.best_price_var.get(),
            "simulation_mode": self.simulation_mode,
        })

    def _on_engine_success(self, data):
        self._placing_in_progress = False
        if hasattr(self, "place_btn") and self.place_btn.winfo_exists():
            self.place_btn.configure(state=tk.NORMAL)

        msg = f"Scommessa simulata piazzata!\nNuovo Saldo: {format_currency(data.get('new_balance', 0))}" if data.get("sim") else f"Scommesse piazzate!\nImporto matchato: {format_currency(data.get('matched', 0))}"
        messagebox.showinfo("Successo", msg)
        self._update_balance()
        self._clear_selections()
        if hasattr(self, "_update_simulation_balance_display"):
            self._update_simulation_balance_display()

    def _on_engine_error(self, error_msg):
        self._placing_in_progress = False
        if hasattr(self, "place_btn") and self.place_btn.winfo_exists():
            self.place_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Errore Motore", f"Piazzamento fallito:\n{error_msg}")

