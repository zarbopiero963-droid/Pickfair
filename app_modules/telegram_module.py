import logging
import tkinter as tk
from tkinter import messagebox, simpledialog

from theme import COLORS

logger = logging.getLogger(__name__)


class TelegramModule:
    def _start_telegram_listener(self):
        """Start the Telegram listener background thread (decoupled with EventBus)."""
        settings = self.db.get_telegram_settings()
        if not settings or not settings.get("api_id") or not settings.get("api_hash"):
            messagebox.showwarning(
                "Attenzione",
                "Configura e salva le credenziali Telegram prima di avviare il listener.",
            )
            return

        if getattr(self, "telegram_listener", None) and self.telegram_listener.running:
            messagebox.showinfo("Info", "Listener già in esecuzione")
            return

        try:
            from telegram_listener import TelegramListener

            self.telegram_listener = TelegramListener(
                api_id=int(settings["api_id"]),
                api_hash=settings["api_hash"].strip(),
                session_string=settings.get("session_string"),
            )

            monitored_chats = []
            for chat in self.db.get_telegram_chats():
                if not chat.get("is_active", True):
                    continue
                try:
                    monitored_chats.append(int(chat["chat_id"]))
                except Exception:
                    logger.warning(
                        "[TelegramModule] chat_id non valido ignorato: %s",
                        chat,
                    )

            if not monitored_chats:
                messagebox.showwarning(
                    "Attenzione",
                    "Nessuna chat monitorata attiva. Aggiungine almeno una.",
                )
                return

            self.telegram_listener.set_monitored_chats(monitored_chats)
            self.telegram_listener.set_database(self.db)

            self.telegram_listener.set_callbacks(
                on_signal=lambda sig: self.bus.publish("TELEGRAM_SIGNAL", sig),
                on_message=None,
                on_status=lambda st, msg: self.bus.publish(
                    "TELEGRAM_STATUS", {"status": st, "message": msg}
                ),
            )

            self.telegram_listener.start()
            self.telegram_status = "LISTENING"

            if hasattr(self, "tg_status_label") and self.tg_status_label.winfo_exists():
                self.tg_status_label.configure(
                    text=f"Stato: {self.telegram_status}",
                    text_color=COLORS["success"],
                )

            messagebox.showinfo("Successo", "Telegram Listener avviato")

        except Exception as e:
            messagebox.showerror(
                "Errore",
                f"Impossibile avviare listener: {str(e)}",
            )

    def _stop_telegram_listener(self):
        if getattr(self, "telegram_listener", None) and self.telegram_listener.running:
            self.telegram_listener.stop()
            self.telegram_status = "STOPPED"

            if hasattr(self, "tg_status_label") and self.tg_status_label.winfo_exists():
                self.tg_status_label.configure(
                    text=f"Stato: {self.telegram_status}",
                    text_color=COLORS["error"],
                )

            messagebox.showinfo("Info", "Telegram Listener fermato")

    def _handle_telegram_signal(self, signal):
        """Riceve il segnale parsato e lo inoltra al RiskMiddleware via REQ_*."""
        action = str(signal.get("action", "BACK")).upper()
        selection_id = signal.get("selection_id")
        market_id = signal.get("market_id")
        selection_name = signal.get("selection", str(selection_id))

        try:
            price = float(signal.get("price", 2.0))
        except Exception:
            logger.error("[TelegramModule] Segnale ignorato: price non valido.")
            if hasattr(self.db, "save_received_signal"):
                self.db.save_received_signal(
                    selection=selection_name,
                    action=action,
                    price=0.0,
                    stake=0.0,
                    status="ERROR",
                )
            self._refresh_telegram_signals_tree()
            return

        try:
            stake = float(self.tg_auto_stake_var.get().replace(",", "."))
        except Exception:
            stake = 1.0

        if hasattr(self.db, "save_received_signal"):
            self.db.save_received_signal(
                selection=selection_name,
                action=action,
                price=price,
                stake=stake,
                status="RECEIVED",
            )
        self._refresh_telegram_signals_tree()

        auto_bet_enabled = (
            hasattr(self, "tg_auto_bet_var")
            and self.tg_auto_bet_var is not None
            and self.tg_auto_bet_var.get()
        )
        confirm_enabled = (
            hasattr(self, "tg_confirm_var")
            and self.tg_confirm_var is not None
            and self.tg_confirm_var.get()
        )

        if not auto_bet_enabled:
            if confirm_enabled:
                msg = (
                    f"Segnale ricevuto:\n"
                    f"{selection_name}\n"
                    f"Tipo: {action}\n"
                    f"Quota: {price}\n\n"
                    f"Piazzare la scommessa?"
                )
                if not messagebox.askyesno("Nuovo Segnale Telegram", msg):
                    if hasattr(self.db, "save_received_signal"):
                        self.db.save_received_signal(
                            selection=selection_name,
                            action=action,
                            price=price,
                            stake=stake,
                            status="IGNORED",
                        )
                    self._refresh_telegram_signals_tree()
                    return
            else:
                if hasattr(self.db, "save_received_signal"):
                    self.db.save_received_signal(
                        selection=selection_name,
                        action=action,
                        price=price,
                        stake=stake,
                        status="IGNORED",
                    )
                self._refresh_telegram_signals_tree()
                return

        if not selection_id or not market_id:
            logger.error(
                "[TelegramModule] Segnale ignorato: market_id o selection_id mancanti."
            )
            if hasattr(self.db, "save_received_signal"):
                self.db.save_received_signal(
                    selection=selection_name,
                    action=action,
                    price=price,
                    stake=stake,
                    status="ERROR",
                )
            self._refresh_telegram_signals_tree()
            return

        try:
            payload = {
                "market_id": str(market_id),
                "market_type": signal.get("market_type", "MATCH_ODDS"),
                "event_name": signal.get("match", "Segnale Telegram"),
                "market_name": signal.get("market", "Scommessa da Segnale"),
                "selection_id": int(selection_id),
                "runner_name": selection_name,
                "bet_type": action,
                "price": price,
                "stake": stake,
                "simulation_mode": getattr(self, "simulation_mode", False),
                "source": "TELEGRAM",
            }
        except Exception as e:
            logger.error(
                "[TelegramModule] Segnale ignorato: payload invalido (%s)",
                e,
            )
            if hasattr(self.db, "save_received_signal"):
                self.db.save_received_signal(
                    selection=selection_name,
                    action=action,
                    price=price,
                    stake=stake,
                    status="ERROR",
                )
            self._refresh_telegram_signals_tree()
            return

        logger.info(
            "[TelegramModule] Inoltro segnale all'OMS via RiskGate: %s",
            payload,
        )
        self.bus.publish("REQ_QUICK_BET", payload)

        if hasattr(self.db, "save_received_signal"):
            self.db.save_received_signal(
                selection=selection_name,
                action=action,
                price=price,
                stake=stake,
                status="SUBMITTED",
            )
        self._refresh_telegram_signals_tree()

    def _update_telegram_status(self, status, message):
        self.telegram_status = status
        color = COLORS["success"] if status == "LISTENING" else COLORS["error"]

        if hasattr(self, "tg_status_label") and self.tg_status_label.winfo_exists():
            self.tg_status_label.configure(
                text=f"Stato: {status} - {message}",
                text_color=color,
            )

    def _refresh_telegram_chats_tree(self):
        if not hasattr(self, "tg_chats_tree") or not self.tg_chats_tree.winfo_exists():
            return

        self.tg_chats_tree.delete(*self.tg_chats_tree.get_children())
        chats = self.db.get_telegram_chats()

        for chat in chats:
            state = "Sì" if chat.get("is_active") else "No"
            title = chat.get("title") or chat.get("username") or str(chat.get("chat_id"))
            self.tg_chats_tree.insert(
                "",
                tk.END,
                iid=str(chat["chat_id"]),
                values=(title, state),
            )

    def _remove_telegram_chat(self):
        selected = getattr(self, "tg_chats_tree", None) and self.tg_chats_tree.selection()
        if not selected:
            return

        chats = self.db.get_telegram_chats()
        updated_chats = [c for c in chats if str(c["chat_id"]) not in selected]
        self.db.replace_telegram_chats(updated_chats)
        self._refresh_telegram_chats_tree()

    def _add_selected_available_chats(self):
        selected = getattr(self, "tg_available_tree", None) and self.tg_available_tree.selection()
        if not selected:
            return

        for item_id in selected:
            item = self.tg_available_tree.item(item_id)
            values = item.get("values", [])
            name = values[2] if len(values) > 2 else str(item_id)
            self.db.save_telegram_chat(
                chat_id=item_id,
                title=name,
                is_active=True,
            )

        self._refresh_telegram_chats_tree()
        messagebox.showinfo("Successo", "Chat aggiunte al monitoraggio.")

    def _refresh_rules_tree(self):
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        self.rules_tree.delete(*self.rules_tree.get_children())
        rules = self.db.get_signal_patterns()

        for rule in rules:
            state = "Sì" if rule.get("enabled") else "No"
            self.rules_tree.insert(
                "",
                tk.END,
                iid=str(rule["id"]),
                values=(
                    state,
                    rule.get("label", ""),
                    "MATCH_ODDS",
                    rule.get("pattern", ""),
                ),
            )

    def _add_signal_pattern(self):
        label = simpledialog.askstring("Nuova Regola", "Nome della regola:")
        if not label:
            return

        pattern = simpledialog.askstring("Nuova Regola", "Pattern Regex:")
        if not pattern:
            return

        self.db.save_signal_pattern(
            pattern=pattern,
            label=label,
            enabled=True,
        )
        self._refresh_rules_tree()

    def _edit_signal_pattern(self):
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una regola da modificare.")
            return

        pattern_id = selected[0]
        rules = self.db.get_signal_patterns()
        current = next((r for r in rules if str(r["id"]) == str(pattern_id)), None)

        if not current:
            messagebox.showerror("Errore", "Regola non trovata nel database.")
            return

        new_label = simpledialog.askstring(
            "Modifica Regola",
            "Nome della regola:",
            initialvalue=current.get("label", ""),
        )
        if new_label is None:
            return

        new_pattern = simpledialog.askstring(
            "Modifica Regola",
            "Pattern Regex:",
            initialvalue=current.get("pattern", ""),
        )
        if new_pattern is None:
            return

        try:
            self.db.update_signal_pattern(
                pattern_id=pattern_id,
                pattern=new_pattern,
                label=new_label,
            )
            self._refresh_rules_tree()
            messagebox.showinfo("Successo", "Regola aggiornata correttamente.")
        except Exception as e:
            messagebox.showerror(
                "Errore",
                f"Impossibile aggiornare la regola: {e}",
            )

    def _delete_signal_pattern(self):
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona una regola da eliminare.")
            return

        pattern_id = selected[0]

        if not messagebox.askyesno(
            "Conferma eliminazione",
            "Vuoi davvero eliminare la regola selezionata?",
        ):
            return

        try:
            self.db.delete_signal_pattern(pattern_id)
            self._refresh_rules_tree()
            messagebox.showinfo("Successo", "Regola eliminata.")
        except Exception as e:
            messagebox.showerror(
                "Errore",
                f"Impossibile eliminare la regola: {e}",
            )

    def _toggle_signal_pattern(self):
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning(
                "Attenzione",
                "Seleziona una regola da attivare/disattivare.",
            )
            return

        pattern_id = selected[0]

        try:
            new_state = self.db.toggle_signal_pattern(pattern_id)
            self._refresh_rules_tree()
            stato_txt = "attivata" if new_state else "disattivata"
            messagebox.showinfo("Successo", f"Regola {stato_txt}.")
        except Exception as e:
            messagebox.showerror(
                "Errore",
                f"Impossibile cambiare stato della regola: {e}",
            )

    def _refresh_telegram_signals_tree(self):
        """Aggiorna la tabella visiva leggendo dallo storico salvato nel DB."""
        if not hasattr(self, "tg_signals_tree") or not self.tg_signals_tree.winfo_exists():
            return

        self.tg_signals_tree.delete(*self.tg_signals_tree.get_children())

        if hasattr(self.db, "get_received_signals"):
            signals = self.db.get_received_signals(limit=50)
            for sig in signals:
                date_str = str(sig.get("received_at", ""))[:16]
                sel = sig.get("selection", "")
                action = sig.get("action", "")
                price = f"{float(sig.get('price', 0) or 0):.2f}"
                stake = f"{float(sig.get('stake', 0) or 0):.2f}"
                status = sig.get("status", "")

                tag = ""
                if status in ("RECEIVED", "SUBMITTED"):
                    tag = "success"
                elif status in ("ERROR", "IGNORED"):
                    tag = "failed"

                self.tg_signals_tree.insert(
                    "",
                    tk.END,
                    values=(date_str, sel, action, price, stake, status),
                    tags=(tag,) if tag else (),
                )