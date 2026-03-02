import tkinter as tk
from tkinter import messagebox
import threading
from theme import COLORS

LIVE_REFRESH_INTERVAL = 5000

class StreamingModule:
    def _refresh_prices(self):
        """Manually refresh prices for current market."""
        if not self.current_market:
            return
        self._load_market(self.current_market['marketId'])
    
    def _toggle_streaming(self):
        """Toggle streaming on/off."""
        if self.stream_var.get():
            self._start_streaming()
        else:
            self._stop_streaming()
    
    def _start_streaming(self):
        """Start streaming prices for current market."""
        if not self.client or not self.current_market:
            self.stream_var.set(False)
            return
        
        try:
            self.client.start_streaming(
                [self.current_market['marketId']],
                self._on_price_update
            )
            self.streaming_active = True
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
        self.stream_label.configure(text="")
    
    def _on_price_update(self, market_id, runners_data):
        """Handle streaming price update with throttling lock."""
        if not self.current_market or market_id != self.current_market['marketId']:
            return
        
        with self._buffer_lock:
            self._market_update_buffer[market_id] = runners_data
            if not getattr(self, '_pending_tree_update', False):
                self._pending_tree_update = True
                self.root.after(200, self._throttled_refresh)

    def _throttled_refresh(self):
        """Process buffered streaming updates at safe intervals."""
        with self._buffer_lock:
            snapshot = dict(self._market_update_buffer)
            self._market_update_buffer.clear()
            self._pending_tree_update = False
            
        if not self.current_market:
            return
            
        market_id = self.current_market['marketId']
        runners_data = snapshot.get(market_id)
        if not runners_data:
            return
            
        def update_ui():
            for runner_update in runners_data:
                selection_id = str(runner_update['selectionId'])
                try:
                    item = self.runners_tree.item(selection_id)
                    if not item:
                        continue
                        
                    current_values = list(item['values'])
                    back_prices = runner_update.get('backPrices', [])
                    lay_prices = runner_update.get('layPrices', [])
                    
                    if back_prices:
                        best_back = back_prices[0]
                        current_values[2] = f"{best_back[0]:.2f}"
                        current_values[3] = f"{best_back[1]:.0f}" if len(best_back) > 1 else "-"
                    
                    if lay_prices:
                        best_lay = lay_prices[0]
                        current_values[4] = f"{best_lay[0]:.2f}"
                        current_values[5] = f"{best_lay[1]:.0f}" if len(best_lay) > 1 else "-"
                    
                    self.runners_tree.item(selection_id, values=current_values)
                    
                    if selection_id in self.selected_runners:
                        if back_prices:
                            self.selected_runners[selection_id]['backPrice'] = back_prices[0][0]
                        if lay_prices:
                            self.selected_runners[selection_id]['layPrice'] = lay_prices[0][0]
                        bet_type = self.bet_type_var.get()
                        if bet_type == 'BACK' and back_prices:
                            self.selected_runners[selection_id]['price'] = back_prices[0][0]
                        elif bet_type == 'LAY' and lay_prices:
                            self.selected_runners[selection_id]['price'] = lay_prices[0][0]
                        self._recalculate()
                        
                except Exception:
                    pass
        
        self.uiq.post(update_ui)

    def _toggle_live_mode(self):
        """Toggle live-only mode."""
        if not self.client:
            messagebox.showwarning("Attenzione", "Devi prima connetterti")
            return
        
        self.live_mode = not self.live_mode
        
        if self.live_mode:
            self.live_btn.configure(fg_color=COLORS['success'], text="LIVE ON")
            self._load_live_events()
            self._start_live_refresh()
        else:
            self.live_btn.configure(fg_color=COLORS['loss'], text="LIVE")
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
                err_msg = str(e)
                self.uiq.post(messagebox.showerror, "Errore", err_msg)
        
        self.executor.submit("fetch_live_events", fetch)
    
    def _start_live_refresh(self):
        """Start auto-refresh for live odds."""
        self._stop_live_refresh()
        self._do_live_refresh()
    
    def _do_live_refresh(self):
        """Single live refresh cycle."""
        if not self.live_mode:
            return
        if self.current_market:
            self._refresh_prices()
        self.live_refresh_id = self.root.after(LIVE_REFRESH_INTERVAL, self._do_live_refresh)
    
    def _stop_live_refresh(self):
        """Stop auto-refresh for live odds."""
        if self.live_refresh_id:
            self.root.after_cancel(self.live_refresh_id)
            self.live_refresh_id = None
