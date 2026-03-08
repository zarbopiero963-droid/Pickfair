"""
Streaming Module (Decoupled via EventBus)
Gestisce l'apertura e chiusura dello stream Betfair.
Non tocca mai la UI: pubblica i tick direttamente nel sistema nervoso centrale.
"""

from tkinter import messagebox

from theme import COLORS

LIVE_REFRESH_INTERVAL = 5000


class StreamingModule:

    def _refresh_prices(self):
        """Manually refresh prices for current market."""
        if not getattr(self, "current_market", None):
            return
        self._load_market(self.current_market["marketId"])

    def _toggle_streaming(self):
        """Toggle streaming on/off."""
        if self.stream_var.get():
            self._start_streaming()
        else:
            self._stop_streaming()

    def _start_streaming(self):
        """Start streaming prices for current market."""
        if not self.client or not getattr(self, "current_market", None):
            self.stream_var.set(False)
            return

        try:
            # 🚀 DECOUPLING PURO E PERFORMANCE BOOST:
            # La callback dello stream spinge un dizionario nel Bus in background.
            # Il thread di rete non aspetta MAI la UI.
            self.client.start_streaming(
                [self.current_market["marketId"]],
                lambda market_id, runners_data: self.bus.publish(
                    "MARKET_TICK",
                    {"market_id": market_id, "runners_data": runners_data},
                ),
            )
            self.streaming_active = True
            if hasattr(self, "stream_label") and self.stream_label.winfo_exists():
                self.stream_label.configure(text="STREAMING ATTIVO")
        except Exception as e:
            self.stream_var.set(False)
            messagebox.showerror("Errore Streaming", str(e))

    def _stop_streaming(self):
        """Stop streaming."""
        if self.client:
            self.client.stop_streaming()
        self.streaming_active = False
        self.stream_var.set(False)
        if hasattr(self, "stream_label") and self.stream_label.winfo_exists():
            self.stream_label.configure(text="")

    # ==============================
    # GESTIONE MODALITA' LIVE
    # ==============================

    def _toggle_live_mode(self):
        """Toggle live-only mode."""
        if not self.client:
            messagebox.showwarning("Attenzione", "Devi prima connetterti")
            return

        self.live_mode = not self.live_mode

        if self.live_mode:
            self.live_btn.configure(fg_color=COLORS["success"], text="LIVE ON")
            self._load_live_events()
            self._start_live_refresh()
        else:
            self.live_btn.configure(fg_color=COLORS["loss"], text="LIVE")
            self._stop_live_refresh()
            self._load_events()

    def _load_live_events(self):
        """Load only live/in-play events."""
        if not self.client:
            return

        def fetch():
            try:
                events = self.client.get_live_events_only()
                self.uiq.post(self._display_events, events)
            except Exception as e:
                self.uiq.post(messagebox.showerror, "Errore", str(e))

        self.executor.submit("fetch_live_events", fetch)

    def _start_live_refresh(self):
        """Start auto-refresh for live odds."""
        self._stop_live_refresh()
        self._do_live_refresh()

    def _do_live_refresh(self):
        """Single live refresh cycle."""
        if not self.live_mode:
            return
        if getattr(self, "current_market", None):
            self._refresh_prices()
        self.live_refresh_id = self.root.after(
            LIVE_REFRESH_INTERVAL, self._do_live_refresh
        )

    def _stop_live_refresh(self):
        """Stop auto-refresh for live odds."""
        if hasattr(self, "live_refresh_id") and self.live_refresh_id:
            self.root.after_cancel(self.live_refresh_id)
            self.live_refresh_id = None
