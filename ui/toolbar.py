"""
Toolbar - Barra strumenti avanzata per Pickfair

Toggle rapidi per:
- Simulation Mode
- Auto-Green
- AI Mixed / WoM Mode
- Indicatori stato mercato
- Preset stake buttons

v3.66 - Toolbar avanzata con integrazione DutchingController
"""

import customtkinter as ctk
from typing import TYPE_CHECKING, Optional, Callable

from theme import COLORS

if TYPE_CHECKING:
    from controllers.dutching_controller import DutchingController


class Toolbar(ctk.CTkFrame):
    """
    Toolbar avanzata con toggle e controlli rapidi.
    
    Features:
    - Toggle Simulation Mode (blocca ordini reali)
    - Toggle Auto-Green (cashout automatico)
    - Toggle AI Mixed Mode (BACK/LAY automatico con WoM)
    - Indicatore stato mercato (OK / warning / block)
    - Preset stake buttons (25%, 50%, 100%)
    """
    
    def __init__(
        self, 
        parent,
        controller: Optional["DutchingController"] = None,
        on_status_change: Optional[Callable] = None,
        **kwargs
    ):
        """
        Args:
            parent: Widget parent
            controller: DutchingController per gestire i flag
            on_status_change: Callback quando cambia uno stato
        """
        super().__init__(parent, fg_color=COLORS.get("bg_secondary", "#2b2b2b"), **kwargs)
        
        self.controller = controller
        self.on_status_change = on_status_change
        
        self.simulation_enabled = False
        self.auto_green_enabled = True
        self.ai_enabled = True
        self.preset_stake_pct = 1.0
        self.market_status = "OK"
        
        self._build()
    
    def _build(self):
        """Costruisce la toolbar."""
        self.columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        
        self.sim_var = ctk.BooleanVar(value=self.simulation_enabled)
        self.sim_toggle = ctk.CTkCheckBox(
            self,
            text="Simulation",
            variable=self.sim_var,
            command=self._toggle_simulation,
            fg_color=COLORS.get("warning", "#ff9800"),
            hover_color=COLORS.get("warning", "#ff9800"),
            text_color=COLORS.get("text", "#ffffff"),
            font=("Roboto", 11)
        )
        self.sim_toggle.grid(row=0, column=0, padx=6, pady=6, sticky="w")
        
        self.green_var = ctk.BooleanVar(value=self.auto_green_enabled)
        self.green_toggle = ctk.CTkCheckBox(
            self,
            text="Auto-Green",
            variable=self.green_var,
            command=self._toggle_auto_green,
            fg_color=COLORS.get("profit", "#4caf50"),
            hover_color=COLORS.get("profit", "#4caf50"),
            text_color=COLORS.get("text", "#ffffff"),
            font=("Roboto", 11)
        )
        self.green_toggle.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        
        self.ai_var = ctk.BooleanVar(value=self.ai_enabled)
        self.ai_toggle = ctk.CTkCheckBox(
            self,
            text="AI Mixed",
            variable=self.ai_var,
            command=self._toggle_ai,
            fg_color=COLORS.get("back", "#1e88e5"),
            hover_color=COLORS.get("back", "#1e88e5"),
            text_color=COLORS.get("text", "#ffffff"),
            font=("Roboto", 11)
        )
        self.ai_toggle.grid(row=0, column=2, padx=6, pady=6, sticky="w")
        
        self.status_label = ctk.CTkLabel(
            self,
            text="Market OK",
            fg_color=COLORS.get("profit", "#4caf50"),
            corner_radius=4,
            font=("Roboto", 11, "bold"),
            padx=8,
            pady=2
        )
        self.status_label.grid(row=0, column=3, padx=10, pady=6)
        
        stake_frame = ctk.CTkFrame(self, fg_color="transparent")
        stake_frame.grid(row=0, column=4, columnspan=3, padx=6, pady=6, sticky="e")
        
        ctk.CTkLabel(
            stake_frame,
            text="Stake:",
            font=("Roboto", 10),
            text_color=COLORS.get("text_secondary", "#888888")
        ).pack(side="left", padx=(0, 4))
        
        for pct in [25, 50, 100]:
            btn = ctk.CTkButton(
                stake_frame,
                text=f"{pct}%",
                width=45,
                height=26,
                font=("Roboto", 10),
                fg_color=COLORS.get("bg_tertiary", "#3d3d3d"),
                hover_color=COLORS.get("back", "#1e88e5"),
                command=lambda p=pct: self._set_preset_stake(p)
            )
            btn.pack(side="left", padx=2)
    
    def _toggle_simulation(self):
        """Toggle simulation mode."""
        self.simulation_enabled = self.sim_var.get()
        
        if self.controller:
            self.controller.simulation = self.simulation_enabled
        
        if self.on_status_change:
            self.on_status_change("simulation", self.simulation_enabled)
    
    def _toggle_auto_green(self):
        """Toggle auto-green."""
        self.auto_green_enabled = self.green_var.get()
        
        if self.controller and hasattr(self.controller, 'auto_green_enabled'):
            self.controller.auto_green_enabled = self.auto_green_enabled
        
        if self.on_status_change:
            self.on_status_change("auto_green", self.auto_green_enabled)
    
    def _toggle_ai(self):
        """Toggle AI Mixed mode."""
        self.ai_enabled = self.ai_var.get()
        
        if self.controller and hasattr(self.controller, 'ai_enabled'):
            self.controller.ai_enabled = self.ai_enabled
        
        if self.on_status_change:
            self.on_status_change("ai_enabled", self.ai_enabled)
    
    def _set_preset_stake(self, pct: int):
        """Imposta preset stake."""
        self.preset_stake_pct = pct / 100.0
        
        if self.controller and hasattr(self.controller, 'preset_stake_pct'):
            self.controller.preset_stake_pct = self.preset_stake_pct
        
        if self.on_status_change:
            self.on_status_change("preset_stake", self.preset_stake_pct)
    
    def set_market_status(self, status: str, message: str = ""):
        """
        Aggiorna indicatore stato mercato.
        
        Args:
            status: 'OK', 'WARNING', 'BLOCK'
            message: Messaggio opzionale
        """
        self.market_status = status
        
        if status == "OK":
            color = COLORS.get("profit", "#4caf50")
            text = message or "Market OK"
        elif status == "WARNING":
            color = COLORS.get("warning", "#ff9800")
            text = message or "Warning"
        else:
            color = COLORS.get("loss", "#f44336")
            text = message or "Blocked"
        
        self.status_label.configure(text=text, fg_color=color)
    
    def set_preflight_status(self, preflight_result):
        """
        Aggiorna status basato su preflight result.
        
        Args:
            preflight_result: PreflightResult dataclass
        """
        if not preflight_result.is_valid:
            self.set_market_status("BLOCK", "Preflight FAIL")
        elif preflight_result.warnings:
            self.set_market_status("WARNING", f"{len(preflight_result.warnings)} warnings")
        else:
            self.set_market_status("OK", "Ready")
    
    def get_state(self) -> dict:
        """Ritorna stato corrente della toolbar."""
        return {
            "simulation_enabled": self.simulation_enabled,
            "auto_green_enabled": self.auto_green_enabled,
            "ai_enabled": self.ai_enabled,
            "preset_stake_pct": self.preset_stake_pct,
            "market_status": self.market_status
        }
    
    def set_simulation(self, enabled: bool):
        """Imposta simulation mode programmaticamente."""
        self.simulation_enabled = enabled
        self.sim_var.set(enabled)
        if self.controller:
            self.controller.simulation = enabled
    
    def set_auto_green(self, enabled: bool):
        """Imposta auto-green programmaticamente."""
        self.auto_green_enabled = enabled
        self.green_var.set(enabled)
        if self.controller and hasattr(self.controller, 'auto_green_enabled'):
            self.controller.auto_green_enabled = enabled
    
    def set_ai_enabled(self, enabled: bool):
        """Imposta AI mode programmaticamente."""
        self.ai_enabled = enabled
        self.ai_var.set(enabled)
        if self.controller and hasattr(self.controller, 'ai_enabled'):
            self.controller.ai_enabled = enabled
