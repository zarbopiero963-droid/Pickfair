import tkinter as tk
from tkinter import messagebox

from dutching import format_currency


class SimulationModule:
    def _place_quick_simulation_bet(self, runner, bet_type, price, stake):
        """Place a quick simulated bet."""
        try:
            commission = 0.045
            if bet_type == "BACK":
                gross_profit = stake * (price - 1)
                profit = gross_profit * (1 - commission)
                liability = stake
            else:
                gross_profit = stake
                profit = gross_profit * (1 - commission)
                liability = stake * (price - 1)

            settings = self.db.get_simulation_settings()
            current_balance = settings.get("virtual_balance", 10000.0)

            if liability > current_balance:
                messagebox.showerror(
                    "Errore Simulazione",
                    f"Saldo virtuale insufficiente.\n"
                    f"Saldo: {format_currency(current_balance)}\n"
                    f"Richiesto: {format_currency(liability)}",
                )
                return

            new_balance = current_balance - liability
            self.db.increment_simulation_bet_count(new_balance)

            self.db.save_simulation_bet(
                event_name=self.current_market.get("eventName", "Quick Bet"),
                market_id=self.current_market["marketId"],
                market_name=self.current_market.get("marketName", ""),
                side=bet_type,
                selection_id=str(runner["selectionId"]),
                selection_name=runner["runnerName"],
                price=price,
                stake=stake,
                status="MATCHED",
            )

            messagebox.showinfo(
                "Simulazione",
                f"Scommessa simulata piazzata!\n\n"
                f"{runner['runnerName']} @ {price:.2f}\n"
                f"Stake: {format_currency(stake)}\n"
                f"Nuovo Saldo: {format_currency(new_balance)}",
            )

        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _place_simulation_bets(self, total_stake, potential_profit, bet_type):
        """Place simulated bets without calling Betfair API."""
        try:
            sim_settings = self.db.get_simulation_settings()
            virtual_balance = sim_settings.get("virtual_balance", 0)

            new_balance = virtual_balance - total_stake
            self.db.increment_simulation_bet_count(new_balance)

            selections_info = [
                {
                    "name": r.get("runnerName", "Unknown"),
                    "price": r["price"],
                    "stake": r["stake"],
                }
                for r in self.calculated_results
            ]

            self.db.save_simulation_bet(
                event_name=self.current_event["name"],
                market_id=self.current_market["marketId"],
                market_name=self.current_market["marketName"],
                side=bet_type,
                selections=selections_info,
                total_stake=total_stake,
                potential_profit=potential_profit,
            )

            self._update_simulation_balance_display()
            self.place_btn.configure(state=tk.NORMAL)

            messagebox.showinfo(
                "Simulazione",
                f"Scommessa virtuale piazzata!\n\n"
                f"Stake: {format_currency(total_stake)}\n"
                f"Profitto Potenziale: {format_currency(potential_profit)}\n"
                f"Nuovo Saldo Virtuale: {format_currency(new_balance)}",
            )

            self._clear_selections()

        except Exception as e:
            self.place_btn.configure(state=tk.NORMAL)
            messagebox.showerror("Errore Simulazione", f"Errore: {e}")
