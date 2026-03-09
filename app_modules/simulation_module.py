"""
Simulation Module - UI Only
-------------------------------------------------
Questo modulo NON esegue ordini.
L'esecuzione simulata è demandata all'OMS / TradingEngine.

Compiti:
- gestire toggle UI simulazione
- leggere saldo virtuale dal DB
- leggere storico simulato dal DB
- reset ambiente simulazione
- impostazione manuale saldo virtuale
"""

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog

from theme import COLORS

logger = logging.getLogger("SimulationModule")


class SimulationModule:
    def _toggle_simulation(self):
        """Attiva/disattiva la modalità simulazione lato UI."""
        var = getattr(self, "simulation_var", None)
        if var is not None:
            self.simulation_mode = bool(var.get())
        else:
            self.simulation_mode = bool(getattr(self, "simulation_mode", False))

        if self.simulation_mode:
            if hasattr(self, "status_label") and self.status_label.winfo_exists():
                self.status_label.configure(
                    text="MODALITÀ SIMULAZIONE ATTIVA",
                    text_color=COLORS["warning"],
                )

            if hasattr(self, "connect_btn") and self.connect_btn.winfo_exists():
                try:
                    self.connect_btn.configure(state=tk.DISABLED)
                except Exception:
                    pass

            self._update_simulation_balance_display()
            self._refresh_simulation_bets()
            logger.info("[SimulationModule] Modalità simulazione attivata.")
        else:
            if hasattr(self, "status_label") and self.status_label.winfo_exists():
                if getattr(self, "client", None):
                    self.status_label.configure(
                        text="Connesso a Betfair Italia",
                        text_color=COLORS["success"],
                    )
                else:
                    self.status_label.configure(
                        text="Non connesso",
                        text_color=COLORS["error"],
                    )

            if hasattr(self, "connect_btn") and self.connect_btn.winfo_exists():
                try:
                    self.connect_btn.configure(state=tk.NORMAL)
                except Exception:
                    pass

            logger.info("[SimulationModule] Modalità simulazione disattivata.")

    def _update_simulation_balance_display(self):
        """Legge il saldo virtuale dal DB e aggiorna la UI."""
        if not hasattr(self, "db") or self.db is None:
            return

        settings = self.db.get_simulation_settings()
        virtual_balance = float(settings.get("virtual_balance", 10000.0))
        starting_balance = float(settings.get("starting_balance", 10000.0))
        bet_count = int(settings.get("bet_count", 0))

        if hasattr(self, "sim_balance_label") and self.sim_balance_label.winfo_exists():
            self.sim_balance_label.configure(
                text=f"Saldo Virtuale: {virtual_balance:.2f} €"
            )

        if hasattr(self, "sim_start_balance_label") and self.sim_start_balance_label.winfo_exists():
            self.sim_start_balance_label.configure(
                text=f"Saldo Iniziale: {starting_balance:.2f} €"
            )

        if hasattr(self, "sim_bet_count_label") and self.sim_bet_count_label.winfo_exists():
            self.sim_bet_count_label.configure(
                text=f"Scommesse simulate: {bet_count}"
            )

    def _refresh_simulation_bets(self):
        """Popola la tabella simulata leggendo i dati dal DB."""
        if not hasattr(self, "sim_bets_tree") or not self.sim_bets_tree.winfo_exists():
            return

        self.sim_bets_tree.delete(*self.sim_bets_tree.get_children())

        if not hasattr(self, "db") or self.db is None:
            return

        try:
            bets = self.db.get_simulation_bets(limit=100)
        except Exception as e:
            logger.error(f"[SimulationModule] Errore lettura simulation_bet_history: {e}")
            return

        for bet in bets:
            placed_at = str(bet.get("placed_at", ""))[:16]
            market_name = bet.get("market_name", "") or bet.get("market_id", "")
            selection_name = bet.get("selection_name", "") or bet.get("selection_id", "")
            side = bet.get("side", "")
            price = bet.get("price", None)
            stake = bet.get("stake", None)
            status = bet.get("status", "MATCHED")

            price_str = f"{float(price):.2f}" if price not in (None, "") else "-"
            stake_str = f"{float(stake):.2f}" if stake not in (None, "") else "-"

            tags = ()
            if status in ("MATCHED", "PARTIALLY_MATCHED"):
                tags = ("success",)
            elif status in ("FAILED", "ERROR"):
                tags = ("failed",)

            self.sim_bets_tree.insert(
                "",
                tk.END,
                values=(
                    placed_at,
                    market_name,
                    selection_name,
                    side,
                    price_str,
                    stake_str,
                    status,
                ),
                tags=tags,
            )

        try:
            self.sim_bets_tree.tag_configure("success", foreground=COLORS["success"])
            self.sim_bets_tree.tag_configure("failed", foreground=COLORS["loss"])
        except Exception:
            pass

    def _reset_simulation(self):
        """Reset totale ambiente simulazione."""
        if not hasattr(self, "db") or self.db is None:
            return

        if not messagebox.askyesno(
            "Conferma Reset",
            "Resettare il saldo virtuale a 10.000 € e svuotare lo storico simulato?",
        ):
            return

        try:
            default_settings = {
                "starting_balance": 10000.0,
                "virtual_balance": 10000.0,
                "bet_count": 0,
            }
            self.db.save_simulation_settings(default_settings)
            self.db._execute("DELETE FROM simulation_bet_history")

            self._update_simulation_balance_display()
            self._refresh_simulation_bets()

            messagebox.showinfo(
                "Successo",
                "Ambiente di simulazione ripristinato con successo.",
            )
            logger.info("[SimulationModule] Ambiente simulazione resettato.")
        except Exception as e:
            logger.error(f"[SimulationModule] Errore reset simulazione: {e}")
            messagebox.showerror(
                "Errore DB",
                f"Impossibile resettare la simulazione:\n{e}",
            )

    def _update_sim_balance_custom(self):
        """Permette di impostare manualmente il saldo virtuale."""
        if not hasattr(self, "db") or self.db is None:
            return

        new_value = simpledialog.askfloat(
            "Imposta Saldo",
            "Inserisci il nuovo saldo virtuale (EUR):",
            minvalue=0.0,
        )
        if new_value is None:
            return

        try:
            settings = self.db.get_simulation_settings()
            if "starting_balance" not in settings:
                settings["starting_balance"] = float(new_value)
            settings["virtual_balance"] = float(new_value)
            self.db.save_simulation_settings(settings)

            self._update_simulation_balance_display()
            logger.info(
                f"[SimulationModule] Saldo virtuale aggiornato manualmente a {new_value:.2f} €."
            )
        except Exception as e:
            logger.error(f"[SimulationModule] Errore update saldo virtuale: {e}")
            messagebox.showerror(
                "Errore",
                f"Impossibile aggiornare il saldo:\n{e}",
            )

    def _load_simulation_panel(self):
        """Helper opzionale richiamabile dalla UI al caricamento tab."""
        self._update_simulation_balance_display()
        self._refresh_simulation_bets()

    def _append_simulation_row_from_event(self, payload):
        """
        Helper opzionale:
        dopo un evento OMS di successo simulato, aggiorna subito la UI.
        """
        try:
            if payload and payload.get("sim"):
                self._update_simulation_balance_display()
                self._refresh_simulation_bets()
        except Exception as e:
            logger.error(f"[SimulationModule] Errore refresh post-evento simulato: {e}")
