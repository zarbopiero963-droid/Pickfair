"""
TelegramController
Isola SOLO autenticazione e gestione chat.
Non tocca listener, pattern editor né trading logic.
"""

import os
import asyncio
import tkinter as tk
from tkinter import messagebox


class TelegramController:

    def __init__(self, app):
        self.app = app

    # ==============================
    # SETTINGS
    # ==============================

    def save_settings(self):
        try:
            stake = float(self.app.tg_auto_stake_var.get().replace(',', '.'))
        except Exception:
            stake = 1.0

        settings = self.app.db.get_telegram_settings() or {}

        self.app.db.save_telegram_settings(
            api_id=self.app.tg_api_id_var.get(),
            api_hash=self.app.tg_api_hash_var.get(),
            session_string=settings.get("session_string"),
            phone_number=self.app.tg_phone_var.get(),
            enabled=True,
            auto_bet=self.app.tg_auto_bet_var.get(),
            require_confirmation=self.app.tg_confirm_var.get(),
            auto_stake=stake
        )

        messagebox.showinfo("Salvato", "Impostazioni Telegram salvate.")

    # ==============================
    # AUTHENTICATION
    # ==============================

    def _get_session_path(self):
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        session_dir = os.path.join(base, "Pickfair")
        os.makedirs(session_dir, exist_ok=True)
        return os.path.join(session_dir, "telegram_session")

    def send_code(self):
        api_id = self.app.tg_api_id_var.get()
        api_hash = self.app.tg_api_hash_var.get()
        phone = self.app.tg_phone_var.get()

        if not api_id or not api_hash or not phone:
            messagebox.showwarning("Errore", "Compila API ID, API Hash e Telefono.")
            return

        self.app.tg_status_label.configure(text="Stato: Invio codice in corso...")

        def task():
            try:
                from telethon import TelegramClient

                async def run():
                    client = TelegramClient(
                        self._get_session_path(),
                        int(api_id),
                        api_hash
                    )
                    await client.connect()

                    if await client.is_user_authorized():
                        await client.disconnect()
                        return True, "Già autenticato. Nessun codice necessario."

                    await client.send_code_request(phone)
                    await client.disconnect()
                    return False, "Codice inviato. Inseriscilo e clicca Verifica."

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                authorized, msg = loop.run_until_complete(run())
                loop.close()

                self.app.uiq.post(
                    self.app.tg_status_label.configure,
                    text=f"Stato: {msg}"
                )

            except Exception as e:
                self.app.uiq.post(
                    messagebox.showerror,
                    "Errore",
                    f"Impossibile inviare codice: {str(e)}"
                )

        self.app.executor.submit("tg_send_code", task)

    def verify_code(self):
        api_id = self.app.tg_api_id_var.get()
        api_hash = self.app.tg_api_hash_var.get()
        phone = self.app.tg_phone_var.get()
        code = self.app.tg_code_var.get()
        password = self.app.tg_2fa_var.get()

        if not code:
            messagebox.showwarning("Errore", "Inserisci il codice ricevuto.")
            return
            
        self.app.tg_status_label.configure(text="Stato: Verifica in corso...")

        def task():
            try:
                from telethon import TelegramClient
                from telethon.errors import SessionPasswordNeededError

                async def run():
                    client = TelegramClient(
                        self._get_session_path(),
                        int(api_id),
                        api_hash
                    )
                    await client.connect()

                    try:
                        await client.sign_in(phone, code)
                    except SessionPasswordNeededError:
                        if not password:
                            await client.disconnect()
                            return False, "Password 2FA richiesta. Inseriscila e riprova."
                        await client.sign_in(password=password)

                    session_string = client.session.save()
                    await client.disconnect()
                    return True, session_string

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success, result = loop.run_until_complete(run())
                loop.close()

                if success:
                    self.app.db.save_telegram_settings(
                        api_id=api_id,
                        api_hash=api_hash,
                        session_string=result,
                        phone_number=phone,
                        enabled=True
                    )

                    self.app.uiq.post(
                        self.app.tg_status_label.configure,
                        text="Stato: Autenticato con successo"
                    )
                    self.app.uiq.post(
                        messagebox.showinfo,
                        "Successo",
                        "Login Telegram completato. Ora puoi usare il listener."
                    )
                else:
                    self.app.uiq.post(
                        self.app.tg_status_label.configure,
                        text="Stato: Errore Verifica"
                    )
                    self.app.uiq.post(
                        messagebox.showwarning,
                        "Attenzione",
                        result
                    )

            except Exception as e:
                self.app.uiq.post(
                    self.app.tg_status_label.configure,
                    text="Stato: Errore Verifica"
                )
                self.app.uiq.post(
                    messagebox.showerror,
                    "Errore",
                    f"Verifica fallita: {str(e)}"
                )

        self.app.executor.submit("tg_verify_code", task)

    def reset_session(self):
        if not messagebox.askyesno(
            "Conferma",
            "Vuoi cancellare la sessione Telegram attuale? Dovrai ripetere l'autenticazione."
        ):
            return

        path = self._get_session_path() + ".session"
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

        settings = self.app.db.get_telegram_settings() or {}
        self.app.db.save_telegram_settings(
            api_id=settings.get('api_id', ''),
            api_hash=settings.get('api_hash', ''),
            session_string='',
            phone_number=settings.get('phone_number', ''),
            enabled=False
        )

        self.app.tg_status_label.configure(text="Stato: Sessione resettata.")
        messagebox.showinfo("OK", "Sessione rimossa. Reinserisci i dati e richiedi un nuovo codice.")

    # ==============================
    # CHAT MANAGEMENT
    # ==============================

    def load_dialogs(self):
        settings = self.app.db.get_telegram_settings()

        if not settings or not settings.get("api_id") or not settings.get("api_hash"):
            messagebox.showwarning("Errore", "Configura Telegram prima.")
            return

        self.app.tg_available_status.configure(text="Caricamento...")

        def task():
            try:
                from telethon import TelegramClient

                async def run():
                    client = TelegramClient(
                        self._get_session_path(),
                        int(settings["api_id"]),
                        settings["api_hash"]
                    )
                    await client.connect()

                    if not await client.is_user_authorized():
                        await client.disconnect()
                        return None

                    dialogs = await client.get_dialogs()
                    await client.disconnect()
                    return dialogs

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                dialogs = loop.run_until_complete(run())
                loop.close()

                if dialogs is None:
                    self.app.uiq.post(self.app.tg_available_status.configure, text="Non autenticato")
                    self.app.uiq.post(messagebox.showwarning, "Attenzione", "Non autenticato. Effettua il login.")
                    return

                def update_ui():
                    self.app.tg_available_tree.delete(
                        *self.app.tg_available_tree.get_children()
                    )

                    monitored_ids = {int(chat['chat_id']) for chat in self.app.db.get_telegram_chats()}

                    for d in dialogs:
                        if d.id in monitored_ids:
                            continue
                        # HARDENING: Fallback sicuro se d.name è None
                        safe_name = d.name or str(d.id)
                        self.app.tg_available_tree.insert(
                            "",
                            tk.END,
                            iid=str(d.id),
                            values=("", "Chat", safe_name)
                        )
                    
                    count = len(self.app.tg_available_tree.get_children())
                    self.app.tg_available_status.configure(text=f"{count} chat disponibili")

                self.app.uiq.post(update_ui)

            except Exception as e:
                self.app.uiq.post(self.app.tg_available_status.configure, text="Errore caricamento")
                self.app.uiq.post(messagebox.showerror, "Errore", str(e))

        self.app.executor.submit("tg_load_dialogs", task)
