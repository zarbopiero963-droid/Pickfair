"""
DraggableRunner - Drag & Drop per riordinare runner

UX professionale per riordinare visivamente i runner nella lista dutching.
Zero impatto sui calcoli matematici.
"""

import customtkinter as ctk
from typing import Dict, Optional, Callable

from theme import COLORS


class DraggableRunner(ctk.CTkFrame):
    """
    Runner trascinabile con drag & drop.
    
    Features:
    - Drag verticale per riordinare
    - Visual feedback durante drag
    - Callback on_move per aggiornare lista
    """
    
    def __init__(
        self, 
        parent, 
        runner: Dict,
        index: int,
        on_move: Optional[Callable] = None,
        on_select: Optional[Callable] = None
    ):
        """
        Args:
            parent: Widget parent
            runner: Dict con runnerName, selectionId, price, stake
            index: Indice corrente nella lista
            on_move: Callback(runner, old_index, new_index) dopo drop
            on_select: Callback(runner) su click per selezione
        """
        super().__init__(
            parent, 
            fg_color=COLORS.get("bg_secondary", "#2b2b2b"),
            corner_radius=6,
            border_width=1,
            border_color=COLORS.get("border", "#3d3d3d")
        )
        
        self.runner = runner
        self.index = index
        self.on_move = on_move
        self.on_select = on_select
        
        self._drag_start_y = 0
        self._original_y = 0
        self._is_dragging = False
        self._selected = False
        
        self._build()
        self._bind_events()
    
    def _build(self):
        """Costruisce UI del runner."""
        # Container principale
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="x", padx=8, pady=6)
        
        # Handle drag (icona grip)
        grip = ctk.CTkLabel(
            content,
            text="⋮⋮",
            font=("Roboto", 14),
            text_color=COLORS.get("text_secondary", "#888888"),
            width=20
        )
        grip.pack(side="left", padx=(0, 8))
        grip.configure(cursor="grab")
        
        # Nome runner
        self.name_label = ctk.CTkLabel(
            content,
            text=self.runner.get("runnerName", "Runner"),
            font=("Roboto", 12, "bold"),
            anchor="w"
        )
        self.name_label.pack(side="left", fill="x", expand=True)
        
        # Prezzo
        price = self.runner.get("price", 0)
        self.price_label = ctk.CTkLabel(
            content,
            text=f"{price:.2f}" if price else "-",
            font=("Roboto", 11),
            text_color=COLORS.get("back", "#1e88e5"),
            width=50
        )
        self.price_label.pack(side="right", padx=(8, 0))
        
        # Stake (se presente)
        stake = self.runner.get("stake", 0)
        if stake > 0:
            self.stake_label = ctk.CTkLabel(
                content,
                text=f"€{stake:.2f}",
                font=("Roboto", 11),
                text_color=COLORS.get("text_secondary", "#888888"),
                width=60
            )
            self.stake_label.pack(side="right")
        else:
            self.stake_label = None
    
    def _bind_events(self):
        """Bind eventi drag & drop e click."""
        # Drag events
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        # Propaga eventi ai child widgets
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_press)
            child.bind("<B1-Motion>", self._on_drag)
            child.bind("<ButtonRelease-1>", self._on_release)
            
            for subchild in child.winfo_children():
                subchild.bind("<Button-1>", self._on_press)
                subchild.bind("<B1-Motion>", self._on_drag)
                subchild.bind("<ButtonRelease-1>", self._on_release)
    
    def _on_press(self, event):
        """Inizio drag o click."""
        self._drag_start_y = event.y_root
        self._original_y = self.winfo_y()
        self._is_dragging = False
        
        # Visual feedback
        self.configure(
            fg_color=COLORS.get("bg_hover", "#3d3d3d"),
            border_color=COLORS.get("accent", "#4a9eff")
        )
    
    def _on_drag(self, event):
        """Durante il drag."""
        delta_y = event.y_root - self._drag_start_y
        
        # Attiva drag solo dopo movimento minimo (evita click accidentali)
        if abs(delta_y) > 5:
            self._is_dragging = True
            
            # Sposta widget
            new_y = self._original_y + delta_y
            self.place(y=new_y)
            
            # Lift sopra altri widget
            self.lift()
            
            # Cursor feedback
            self.configure(cursor="grabbing")
    
    def _on_release(self, event):
        """Fine drag o click."""
        # Reset visual
        self.configure(
            fg_color=COLORS.get("bg_secondary", "#2b2b2b"),
            border_color=COLORS.get("border", "#3d3d3d"),
            cursor=""
        )
        
        if self._is_dragging:
            # Calcola nuovo indice basato su posizione
            delta_y = event.y_root - self._drag_start_y
            row_height = self.winfo_height() + 4  # +4 per padding
            
            index_delta = round(delta_y / row_height)
            new_index = self.index + index_delta
            
            # Callback per riordinamento
            if self.on_move and index_delta != 0:
                self.on_move(self.runner, self.index, new_index)
            
            self._is_dragging = False
        else:
            # Era un click, non drag
            if self.on_select:
                self.on_select(self.runner)
                self.set_selected(not self._selected)
    
    def update_runner(self, runner: Dict, index: int):
        """
        Aggiorna dati runner.
        
        Args:
            runner: Nuovi dati runner
            index: Nuovo indice
        """
        self.runner = runner
        self.index = index
        
        self.name_label.configure(text=runner.get("runnerName", "Runner"))
        
        price = runner.get("price", 0)
        self.price_label.configure(text=f"{price:.2f}" if price else "-")
        
        stake = runner.get("stake", 0)
        if self.stake_label:
            self.stake_label.configure(text=f"€{stake:.2f}" if stake > 0 else "")
    
    def set_selected(self, selected: bool):
        """
        Imposta stato selezione.
        
        Args:
            selected: True se selezionato
        """
        self._selected = selected
        
        if selected:
            self.configure(
                border_color=COLORS.get("accent", "#4a9eff"),
                border_width=2
            )
        else:
            self.configure(
                border_color=COLORS.get("border", "#3d3d3d"),
                border_width=1
            )
    
    def set_side_indicator(self, side: str):
        """
        Mostra indicatore BACK/LAY.
        
        Args:
            side: 'BACK' o 'LAY'
        """
        color = COLORS.get("back", "#1e88e5") if side == "BACK" else COLORS.get("lay", "#e5399b")
        self.price_label.configure(text_color=color)


class DraggableRunnerList(ctk.CTkFrame):
    """
    Lista di runner draggable.
    
    Gestisce automaticamente il riordinamento dopo drag & drop.
    """
    
    def __init__(
        self, 
        parent,
        runners: list,
        on_order_change: Optional[Callable] = None,
        on_runner_select: Optional[Callable] = None
    ):
        """
        Args:
            parent: Widget parent
            runners: Lista iniziale di runner
            on_order_change: Callback(new_order: List[Dict]) dopo riordinamento
            on_runner_select: Callback(runner) su selezione runner
        """
        super().__init__(parent, fg_color="transparent")
        
        self.runners = list(runners)
        self.on_order_change = on_order_change
        self.on_runner_select = on_runner_select
        
        self.runner_widgets = []
        
        self._build()
    
    def _build(self):
        """Costruisce lista runner."""
        for i, runner in enumerate(self.runners):
            widget = DraggableRunner(
                self,
                runner=runner,
                index=i,
                on_move=self._on_runner_move,
                on_select=self.on_runner_select
            )
            widget.pack(fill="x", pady=2)
            self.runner_widgets.append(widget)
    
    def _on_runner_move(self, runner: Dict, old_index: int, new_index: int):
        """
        Handler per spostamento runner.
        
        Args:
            runner: Runner spostato
            old_index: Indice originale
            new_index: Nuovo indice (può essere fuori range)
        """
        # Clamp new_index
        new_index = max(0, min(new_index, len(self.runners) - 1))
        
        if old_index == new_index:
            return
        
        # Riordina lista
        self.runners.pop(old_index)
        self.runners.insert(new_index, runner)
        
        # Ricostruisci UI
        self.refresh()
        
        # Callback
        if self.on_order_change:
            self.on_order_change(self.runners)
    
    def refresh(self):
        """Ricostruisce lista widget."""
        # Distruggi widget esistenti
        for widget in self.runner_widgets:
            widget.destroy()
        self.runner_widgets.clear()
        
        # Ricrea
        for i, runner in enumerate(self.runners):
            widget = DraggableRunner(
                self,
                runner=runner,
                index=i,
                on_move=self._on_runner_move,
                on_select=self.on_runner_select
            )
            widget.pack(fill="x", pady=2)
            self.runner_widgets.append(widget)
    
    def update_runners(self, runners: list):
        """
        Aggiorna lista runner.
        
        Args:
            runners: Nuova lista runner
        """
        self.runners = list(runners)
        self.refresh()
    
    def get_order(self) -> list:
        """Ritorna lista runner nell'ordine corrente."""
        return self.runners
