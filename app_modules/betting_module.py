
from betfair_client import BetfairClient
from theme import COLORS
from ui.tk_safe import messagebox, tk


class BettingModule:
    def _schedule_order_cleanup(self):
        try:
            if hasattr(self, "order_manager") and self.order_manager:
                self.order_manager.cleanup_old(max_age_seconds=3600)
        except Exception:
            pass
        self.root.after(3600000, self._schedule_order_cleanup)

    def _on_goal_hedge(self, match_id):
        import logging
        logging.getLogger("PickfairApp").info(f"HEDGE START match={match_id}")
        if hasattr(self, "trading_engine"):
            pass

    def _on_goal_reopen(self, match_id):
        import logging
        logging.getLogger("PickfairApp").info(f"REOPEN positions match={match_id}")
        if hasattr(self, "trading_engine"):
            pass

    def _toggle_connection(self):
        if self.client:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        settings = self.db.get_settings()

        if not all([
            settings.get("username"),
            settings.get("app_key"),
            settings.get("certificate"),
            settings.get("private_key"),
        ]):
            messagebox.showerror("Errore", "Configura prima le credenziali dal menu File")
            return

        from ui.tk_safe import ttk

        pwd_dialog = tk.Toplevel(self.root)
        pwd_dialog.title("Password Betfair")
        pwd_dialog.geometry("350x180")
        pwd_dialog.transient(self.root)
        pwd_dialog.grab_set()

        pwd_dialog.update_idletasks()
        x = (pwd_dialog.winfo_screenwidth() // 2) - 175
        y = (pwd_dialog.winfo_screenheight() // 2) - 90
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

            self.status_label.configure(
                text="Connessione in corso...", text_color=COLORS["text_secondary"]
            )
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
        self.status_label.configure(
            text="Connesso a Betfair Italia", text_color=COLORS["success"]
        )
        self.connect_btn.configure(text="Disconnetti", state=tk.NORMAL)
        self.refresh_btn.configure(state=tk.NORMAL)

        self._update_balance()
        self._load_events()

        self.auto_refresh_var.set(True)
        self._start_auto_refresh()

        self._start_session_keepalive()
        self._refresh_dashboard_tab()

        self.bus.publish("CLIENT_CONNECTED", None)
