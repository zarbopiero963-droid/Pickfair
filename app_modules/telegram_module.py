import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from theme import COLORS
from telegram_listener import TelegramListener

class TelegramModule:
    def _start_telegram_listener(self):
        """Start the Telegram listener background thread (Decoupled with EventBus)."""
        settings = self.db.get_telegram_settings()
        if not settings or not settings.get('api_id') or not settings.get('api_hash'):
            messagebox.showwarning("Attenzione", "Configura e salva le credenziali Telegram prima di avviare il listener.")
            return
            
        if self.telegram_listener and self.telegram_listener.running:
            messagebox.showinfo("Info", "Listener già in esecuzione")
            return
            
        try:
            self.telegram_listener = TelegramListener(
                api_id=int(settings['api_id']),
                api_hash=settings['api_hash'].strip(),
                session_string=settings.get('session_string')
            )
            
            monitored_chats = [int(chat['chat_id']) for chat in self.db.get_telegram_chats() if chat.get('enabled', True)]
            if not monitored_chats:
                messagebox.showwarning("Attenzione", "Nessuna chat monitorata attiva. Aggiungine almeno una.")
                return
                
            self.telegram_listener.set_monitored_chats(monitored_chats)
            self.telegram_listener.set_database(self.db)
            
            # Listener ora completamente decoupled tramite EventBus
            self.telegram_listener.set_callbacks(
                on_signal=lambda sig: self.bus.publish("TELEGRAM_SIGNAL", sig),
                on_message=None,
                on_status=lambda st, msg: self.bus.publish(
                    "TELEGRAM_STATUS",
                    {"status": st, "message": msg}
                )
            )
            
            self.telegram_listener.start()
            self.telegram_status = 'LISTENING'
            if hasattr(self, 'tg_status_label') and self.tg_status_label.winfo_exists():
                self.tg_status_label.configure(text=f"Stato: {self.telegram_status}", text_color=COLORS['success'])
            messagebox.showinfo("Successo", "Telegram Listener avviato")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile avviare listener: {str(e)}")
