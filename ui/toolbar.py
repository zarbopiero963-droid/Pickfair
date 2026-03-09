Barra superiore dell'applicazione.
Reattiva allo stato globale via EventBus
Inoltra comandi globali come Panic Cashout
Gestisce il toggle simulazione tramite l'app """
import tkinter as tk from tkinter import messagebox
import customtkinter as ctk
from theme import COLORS
class Toolbar(ctk.CTkFrame): def init(self, master, app, event_bus, **kwargs): super().init( master, fg_color=COLORS["bg_panel"], height=50, corner_radius=0, **kwargs, ) self.pack_propagate(False)
self.app = app
    self.bus = event_bus

    self.status_indicator = None
    self.btn_cashout_all = None
    self.sim_switch = None

    self._build_ui()
    self._wire_events()

def _build_ui(self):
    self.status_indicator = ctk.CTkLabel(
        self,
        text="🟢 SISTEMA OPERATIVO",
        font=("Segoe UI", 12, "bold"),
        text_color=COLORS["success"],
    )
    self.status_indicator.pack(side=tk.LEFT, padx=20)

    self.btn_cashout_all = ctk.CTkButton(
        self,
        text="⚠️ PANIC CASHOUT (Tutto)",
        fg_color=COLORS["button_danger"],
        hover_color="#b71c1c",
        font=("Segoe UI", 12, "bold"),
        command=self._cmd_panic_cashout,
    )
    self.btn_cashout_all.pack(side=tk.RIGHT, padx=10, pady=10)

    if not hasattr(self.app, "simulation_var"):
        self.app.simulation_var = tk.BooleanVar(value=False)

    self.sim_switch = ctk.CTkSwitch(
        self,
        text="Modalità Simulazione",
        variable=self.app.simulation_var,
        command=self._cmd_toggle_sim,
        progress_color=COLORS["warning"],
        font=("Segoe UI", 12, "bold"),
    )
    self.sim_switch.pack(side=tk.RIGHT, padx=20, pady=10)

def _wire_events(self):
    if self.bus:
        self.bus.subscribe("STATE_UPDATE_SAFE_MODE", self._on_safe_mode_update)

def _on_safe_mode_update(self, payload):
    """
    Compatibile sia con payload bool sia con payload dict.
    """
    if isinstance(payload, dict):
        enabled = bool(payload.get("enabled", False))
        reason = str(payload.get("reason", "") or "")
    else:
        enabled = bool(payload)
        reason = ""

    def update_visuals():
        if enabled:
            text = "🔴 SAFE MODE ATTIVO"
            if reason:
                text = f"🔴 SAFE MODE: {reason}"

            self.status_indicator.configure(
                text=text,
                text_color=COLORS["warning"],
            )

            # Cashout/exit devono restare disponibili
            self.btn_cashout_all.configure(state=tk.NORMAL)
        else:
            self.status_indicator.configure(
                text="🟢 SISTEMA OPERATIVO",
                text_color=COLORS["success"],
            )
            self.btn_cashout_all.configure(state=tk.NORMAL)

    if hasattr(self.app, "uiq"):
        self.app.uiq.post(update_visuals)
    else:
        update_visuals()

def _cmd_toggle_sim(self):
    if hasattr(self.app, "_toggle_simulation"):
        self.app._toggle_simulation()

def _cmd_panic_cashout(self):
    if not messagebox.askyesno(
        "PANIC CASHOUT",
        "Sei sicuro di voler chiudere TUTTE le posizioni aperte sul mercato corrente?",
    ):
        return

    if not getattr(self.app, "current_market", None):
        messagebox.showwarning("Errore", "Nessun mercato selezionato.")
        return

    market_id = self.app.current_market.get("marketId")
    positions = getattr(self.app, "market_cashout_positions", {}) or {}

    if not positions:
        messagebox.showinfo(
            "Info",
            "Nessuna posizione aperta da chiudere su questo mercato.",
        )
        return

    sent_count = 0
    for sel_id, pos in positions.items():
        info = pos.get("cashout_info", {})
        if not info:
            continue

        current_price = float(info.get("current_price", 0) or 0)
        cashout_stake = float(info.get("cashout_stake", 0) or 0)
        cashout_side = info.get("cashout_side")
        green_up = float(info.get("green_up", 0) or 0)

        if current_price <= 0 or cashout_stake <= 0 or not cashout_side:
            continue

        payload = {
            "market_id": str(market_id),
            "selection_id": sel_id,
            "side": cashout_side,
            "stake": cashout_stake,
            "price": current_price,
            "green_up": green_up,
            "original_pos": pos,
            "source": "PANIC_BUTTON",
        }
        self.bus.publish("REQ_EXECUTE_CASHOUT", payload)
        sent_count += 1

    if sent_count == 0:
        messagebox.showinfo(
            "Info",
            "Nessuna posizione valida da inviare in cashout.",
        )
        return

    messagebox.showinfo(
        "Inviato",
        f"Comandi di Cashout inviati all'OMS: {sent_count}",
    )

