import logging
import tkinter as tk
from tkinter import messagebox, simpledialog

from theme import COLORS

logger = logging.getLogger(__name__)


class TelegramModule:
    def _db_call(self, method_name, *args, default=None, **kwargs):
        method = getattr(self.db, method_name, None)
        if not callable(method):
            logger.warning("[TelegramModule] DB method mancante: %s", method_name)
            return default
        try:
            return method(*args, **kwargs)
        except Exception as e:
            logger.exception("[TelegramModule] Errore DB su %s: %s", method_name, e)
            return default

    def _get_telegram_settings(self):
        return self._db_call("get_telegram_settings", default={}) or {}

    def _get_telegram_chats(self):
        return self._db_call("get_telegram_chats", default=[]) or []

    def _get_signal_patterns(self):
        return self._db_call("get_signal_patterns", default=[]) or []

    def _save_telegram_chat(self, chat_id, title, is_active=True):
        return self._db_call(
            "save_telegram_chat",
            chat_id=chat_id,
            title=title,
            is_active=is_active,
            default=None,
        )

    def _replace_telegram_chats(self, chats):
        return self._db_call("replace_telegram_chats", chats, default=None)

    def _save_signal_pattern(self, pattern, label, enabled=True):
        return self._db_call(
            "save_signal_pattern",
            pattern=pattern,
            label=label,
            enabled=enabled,
            default=None,
        )

    def _start_telegram_listener(self):
        """Avvia il listener Telegram. Telegram produce intenti, non esegue ordini."""
        settings = self._get_telegram_settings()
        if not settings.get("api_id") or not settings.get("api_hash"):
            messagebox.showwarning(
                "Attenzione",
                "Configura e salva le credenziali Telegram prima di avviare il listener.",
            )
            return

        if getattr(self, "telegram_listener", None) and getattr(
            self.telegram_listener, "running", False
        ):
            messagebox.showinfo("Info", "Listener già in esecuzione")
            return

        monitored_chats = [
            int(chat["chat_id"])
            for chat in self._get_telegram_chats()
            if chat.get("is_active", True)
        ]
        if not monitored_chats:
            messagebox.showwarning(
                "Attenzione",
                "Nessuna chat monitorata attiva. Aggiungine almeno una.",
            )
            return

        try:
            from telegram_listener import TelegramListener

            self.telegram_listener = TelegramListener(
                api_id=int(settings["api_id"]),
                api_hash=str(settings["api_hash"]).strip(),
                session_string=settings.get("session_string"),
            )

            if hasattr(self.telegram_listener, "set_monitored_chats"):
                self.telegram_listener.set_monitored_chats(monitored_chats)
            if hasattr(self.telegram_listener, "set_database"):
                self.telegram_listener.set_database(self.db)

            if hasattr(self.telegram_listener, "set_callbacks"):
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
            logger.exception("[TelegramModule] Avvio listener fallito: %s", e)
            messagebox.showerror("Errore", f"Impossibile avviare listener: {str(e)}")

    def _stop_telegram_listener(self):
        listener = getattr(self, "telegram_listener", None)
        if listener and getattr(listener, "running", False):
            try:
                listener.stop()
            except Exception as e:
                logger.exception("[TelegramModule] Errore stop listener: %s", e)

        self.telegram_status = "STOPPED"
        if hasattr(self, "tg_status_label") and self.tg_status_label.winfo_exists():
            self.tg_status_label.configure(
                text=f"Stato: {self.telegram_status}",
                text_color=COLORS["error"],
            )
        messagebox.showinfo("Info", "Telegram Listener fermato")

    def _handle_telegram_signal(self, signal):
        """
        Telegram è solo sorgente di intenti.
        Nessun CMD_*, nessuna chiamata diretta client/broker.
        """
        self._refresh_telegram_signals_tree()

        auto_bet_enabled = bool(
            getattr(self, "tg_auto_bet_var", None) and self.tg_auto_bet_var.get()
        )
        require_confirmation = bool(
            getattr(self, "tg_confirm_var", None) and self.tg_confirm_var.get()
        )

        if not auto_bet_enabled:
            if require_confirmation:
                msg = (
                    f"Segnale ricevuto:\n"
                    f"{signal.get('selection', 'Ignota')}\n"
                    f"Tipo: {signal.get('action', 'BACK')}\n"
                    f"Quota: {signal.get('price', '-')}\n\n"
                    f"Vuoi inoltrare l'intento al RiskGate?"
                )
                if not messagebox.askyesno("Nuovo Segnale Telegram", msg):
                    return
            else:
                return

        try:
            stake = float(str(self.tg_auto_stake_var.get()).replace(",", "."))
        except Exception:
            stake = 1.0

        action = str(signal.get("action", "BACK")).upper()
        price = float(signal.get("price", 2.0))
        selection_id = signal.get("selection_id")
        market_id = signal.get("market_id")

        if not selection_id or not market_id:
            logger.error(
                "[TelegramModule] Segnale ignorato: market_id o selection_id mancanti."
            )
            return

        payload = {
            "market_id": str(market_id),
            "market_type": signal.get("market_type", "MATCH_ODDS"),
            "event_name": signal.get("match", "Segnale Telegram"),
            "market_name": signal.get("market", "Scommessa da Segnale"),
            "selection_id": int(selection_id),
            "runner_name": signal.get("selection", str(selection_id)),
            "bet_type": action,
            "price": price,
            "stake": stake,
            "simulation_mode": getattr(self, "simulation_mode", False),
            "source": "TELEGRAM",
        }

        logger.info("[TelegramModule] Publish REQ_QUICK_BET: %s", payload)
        self.bus.publish("REQ_QUICK_BET", payload)

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

        for chat in self._get_telegram_chats():
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

        chats = self._get_telegram_chats()
        updated_chats = [c for c in chats if str(c["chat_id"]) not in selected]
        self._replace_telegram_chats(updated_chats)
        self._refresh_telegram_chats_tree()

    def _add_selected_available_chats(self):
        selected = getattr(self, "tg_available_tree", None) and self.tg_available_tree.selection()
        if not selected:
            return

        for item_id in selected:
            item = self.tg_available_tree.item(item_id)
            values = item.get("values", [])
            name = values[2] if len(values) >= 3 else str(item_id)
            self._save_telegram_chat(chat_id=item_id, title=name, is_active=True)

        self._refresh_telegram_chats_tree()
        messagebox.showinfo("Successo", "Chat aggiunte al monitoraggio.")

    def _refresh_rules_tree(self):
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        self.rules_tree.delete(*self.rules_tree.get_children())
        rules = self._get_signal_patterns()

        for r in rules:
            state = "Sì" if r.get("enabled") else "No"
            self.rules_tree.insert(
                "",
                tk.END,
                iid=str(r.get("id", "")),
                values=(
                    state,
                    r.get("label", ""),
                    r.get("market_type", "MATCH_ODDS"),
                    r.get("pattern", ""),
                ),
            )

    def _add_signal_pattern(self):
        label = simpledialog.askstring("Nuova Regola", "Nome della regola:")
        if not label:
            return

        pattern = simpledialog.askstring("Nuova Regola", "Pattern Regex:")
        if not pattern:
            return

        self._save_signal_pattern(pattern=pattern, label=label, enabled=True)
        self._refresh_rules_tree()

    def _edit_signal_pattern(self):
        messagebox.showinfo("Info", "Modifica regola non ancora implementata.")

    def _delete_signal_pattern(self):
        messagebox.showinfo("Info", "Eliminazione regola non ancora implementata.")

    def _toggle_signal_pattern(self):
        messagebox.showinfo("Info", "Toggle regola non ancora implementato.")

    def _refresh_telegram_signals_tree(self):
        if not hasattr(self, "tg_signals_tree") or not self.tg_signals_tree.winfo_exists():
            return
        # Placeholder: se hai una tabella DB received_signals, qui puoi popolarla.
        pass

