"""
WoM Engine - Weight of Money Time-Window Analysis
Analisi storica dei tick per calcolare la pressione di mercato.

v3.65 - Enterprise WoM Analysis
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
import time
import threading

WOM_WINDOW_SIZE = 50
WOM_TIME_WINDOW_SEC = 30.0
WOM_TIME_WINDOWS = [5.0, 15.0, 30.0, 60.0]  # Multiple time windows for analysis
EDGE_THRESHOLDS = {
    "strong_back": 0.65,
    "back": 0.55,
    "neutral_high": 0.50,
    "neutral_low": 0.45,
    "lay": 0.45,
    "strong_lay": 0.35
}
DELTA_THRESHOLD = 0.05  # Minimum delta for trend significance


@dataclass
class TickData:
    """Singolo tick di mercato."""
    timestamp: float
    selection_id: int
    back_price: float
    back_volume: float
    lay_price: float
    lay_volume: float


@dataclass
class WoMResult:
    """Risultato analisi WoM per un runner."""
    selection_id: int
    wom: float
    wom_trend: float
    edge_score: float
    suggested_side: str
    confidence: float
    tick_count: int
    time_span: float
    
    # v3.67 - Time-Window Analysis
    wom_5s: float = 0.5
    wom_15s: float = 0.5
    wom_30s: float = 0.5
    wom_60s: float = 0.5
    delta_pressure: float = 0.0  # Change in pressure over time
    momentum: float = 0.0  # Rate of change
    volatility: float = 0.0  # Price volatility indicator


@dataclass
class SelectionWoMHistory:
    """Storage storico tick per una selezione."""
    selection_id: int
    ticks: deque = field(default_factory=lambda: deque(maxlen=WOM_WINDOW_SIZE))
    
    def add_tick(self, tick: TickData):
        """Aggiunge tick alla storia."""
        self.ticks.append(tick)
    
    def get_recent(self, max_age_sec: float = WOM_TIME_WINDOW_SEC) -> List[TickData]:
        """Ritorna tick entro la finestra temporale."""
        now = time.time()
        return [t for t in self.ticks if now - t.timestamp <= max_age_sec]
    
    def clear(self):
        """Pulisce la storia."""
        self.ticks.clear()


class WoMEngine:
    """
    Engine per analisi Weight of Money su finestra temporale.
    
    Il WoM misura la pressione di acquisto/vendita:
    - WoM > 0.55: Pressione BACK (compratori)
    - WoM < 0.45: Pressione LAY (venditori)
    - 0.45-0.55: Neutrale
    
    L'edge score combina WoM con trend per suggerire la direzione.
    """
    
    def __init__(self, window_size: int = WOM_WINDOW_SIZE, 
                 time_window: float = WOM_TIME_WINDOW_SEC):
        self._window_size = window_size
        self._time_window = time_window
        self._histories: Dict[int, SelectionWoMHistory] = {}
        self._lock = threading.RLock()
    
    def record_tick(self, selection_id: int, 
                    back_price: float, back_volume: float,
                    lay_price: float, lay_volume: float):
        """
        Registra un nuovo tick per una selezione.
        
        Args:
            selection_id: ID runner
            back_price: Miglior prezzo BACK
            back_volume: Volume disponibile BACK
            lay_price: Miglior prezzo LAY
            lay_volume: Volume disponibile LAY
        """
        with self._lock:
            if selection_id not in self._histories:
                self._histories[selection_id] = SelectionWoMHistory(selection_id)
            
            tick = TickData(
                timestamp=time.time(),
                selection_id=selection_id,
                back_price=back_price,
                back_volume=back_volume,
                lay_price=lay_price,
                lay_volume=lay_volume
            )
            self._histories[selection_id].add_tick(tick)
    
    def calculate_wom(self, selection_id: int) -> Optional[WoMResult]:
        """
        Calcola WoM per una selezione.
        
        Returns:
            WoMResult con tutti i dati analitici, None se dati insufficienti
        """
        with self._lock:
            if selection_id not in self._histories:
                return None
            
            ticks = self._histories[selection_id].get_recent(self._time_window)
            
            if len(ticks) < 2:
                return None
            
            total_back_vol = sum(t.back_volume for t in ticks)
            total_lay_vol = sum(t.lay_volume for t in ticks)
            total_vol = total_back_vol + total_lay_vol
            
            if total_vol == 0:
                return None
            
            wom = total_back_vol / total_vol
            
            mid_idx = len(ticks) // 2
            if mid_idx > 0:
                first_half = ticks[:mid_idx]
                second_half = ticks[mid_idx:]
                
                first_back = sum(t.back_volume for t in first_half)
                first_lay = sum(t.lay_volume for t in first_half)
                first_total = first_back + first_lay
                
                second_back = sum(t.back_volume for t in second_half)
                second_lay = sum(t.lay_volume for t in second_half)
                second_total = second_back + second_lay
                
                first_wom = first_back / first_total if first_total > 0 else 0.5
                second_wom = second_back / second_total if second_total > 0 else 0.5
                
                wom_trend = second_wom - first_wom
            else:
                wom_trend = 0.0
            
            edge_score = self._calculate_edge_score(wom, wom_trend)
            suggested_side = self._determine_side(wom, wom_trend)
            confidence = self._calculate_confidence(wom, len(ticks), wom_trend)
            
            time_span = ticks[-1].timestamp - ticks[0].timestamp if len(ticks) > 1 else 0.0
            
            return WoMResult(
                selection_id=selection_id,
                wom=wom,
                wom_trend=wom_trend,
                edge_score=edge_score,
                suggested_side=suggested_side,
                confidence=confidence,
                tick_count=len(ticks),
                time_span=time_span
            )
    
    def get_ai_edge_score(self, selections: List[Dict]) -> Dict[int, WoMResult]:
        """
        Calcola edge score per multiple selezioni.
        
        Args:
            selections: Lista di dict con selectionId, price, etc.
            
        Returns:
            Dict mappando selectionId -> WoMResult
        """
        results = {}
        
        for sel in selections:
            sel_id = sel.get("selectionId") or sel.get("selection_id")
            if sel_id:
                wom_result = self.calculate_wom(sel_id)
                if wom_result:
                    results[sel_id] = wom_result
        
        return results
    
    def get_mixed_suggestions(self, selections: List[Dict]) -> List[Dict]:
        """
        Suggerisce side BACK/LAY per ogni runner basandosi su WoM.
        
        Per mixed dutching deve esserci almeno 1 BACK e 1 LAY.
        
        Returns:
            Lista di dict con selectionId, suggested_side, edge_score, confidence
        """
        results = []
        edge_data = self.get_ai_edge_score(selections)
        
        for sel in selections:
            sel_id = sel.get("selectionId") or sel.get("selection_id")
            price = sel.get("price", 2.0)
            implied_prob = 1.0 / price if price > 1 else 1.0
            
            if sel_id is not None and sel_id in edge_data:
                wom_result = edge_data[sel_id]
                results.append({
                    "selectionId": sel_id,
                    "runnerName": sel.get("runnerName", f"Runner {sel_id}"),
                    "price": price,
                    "implied_prob": implied_prob,
                    "suggested_side": wom_result.suggested_side,
                    "edge_score": wom_result.edge_score,
                    "confidence": wom_result.confidence,
                    "wom": wom_result.wom,
                    "wom_trend": wom_result.wom_trend,
                    "has_wom_data": True
                })
            else:
                avg_prob = sum(1.0 / s.get("price", 2.0) for s in selections) / len(selections)
                suggested_side = "BACK" if implied_prob < avg_prob else "LAY"
                
                results.append({
                    "selectionId": sel_id,
                    "runnerName": sel.get("runnerName", f"Runner {sel_id}"),
                    "price": price,
                    "implied_prob": implied_prob,
                    "suggested_side": suggested_side,
                    "edge_score": 0.5,
                    "confidence": 0.0,
                    "wom": 0.5,
                    "wom_trend": 0.0,
                    "has_wom_data": False
                })
        
        if len(results) > 1:
            back_count = sum(1 for r in results if r["suggested_side"] == "BACK")
            lay_count = len(results) - back_count
            
            if back_count == 0:
                best_for_back = max(results, key=lambda r: r["wom"])
                best_for_back["suggested_side"] = "BACK"
                best_for_back["forced"] = True
            elif lay_count == 0:
                best_for_lay = min(results, key=lambda r: r["wom"])
                best_for_lay["suggested_side"] = "LAY"
                best_for_lay["forced"] = True
        
        return results
    
    def _calculate_edge_score(self, wom: float, trend: float) -> float:
        """
        Calcola edge score normalizzato [-1, 1].
        
        -1 = strong LAY
        +1 = strong BACK
        """
        base_edge = (wom - 0.5) * 2
        trend_boost = trend * 0.5
        edge = base_edge + trend_boost
        return max(-1.0, min(1.0, edge))
    
    def _determine_side(self, wom: float, trend: float) -> str:
        """Determina side suggerito basandosi su WoM e trend."""
        if wom >= EDGE_THRESHOLDS["strong_back"]:
            return "BACK"
        elif wom >= EDGE_THRESHOLDS["back"]:
            return "BACK" if trend >= 0 else "BACK"
        elif wom <= EDGE_THRESHOLDS["strong_lay"]:
            return "LAY"
        elif wom <= EDGE_THRESHOLDS["lay"]:
            return "LAY" if trend <= 0 else "LAY"
        else:
            return "BACK" if trend > 0.05 else ("LAY" if trend < -0.05 else "BACK")
    
    def _calculate_confidence(self, wom: float, tick_count: int, trend: float) -> float:
        """
        Calcola confidence [0, 1] basandosi su:
        - Distanza dal neutrale (0.5)
        - Numero di tick (più dati = più affidabile)
        - Coerenza del trend
        """
        wom_distance = abs(wom - 0.5) * 2
        tick_factor = min(1.0, tick_count / 30)
        trend_coherence = 1.0 if (wom > 0.5 and trend > 0) or (wom < 0.5 and trend < 0) else 0.7
        
        confidence = wom_distance * 0.4 + tick_factor * 0.4 + trend_coherence * 0.2
        return min(1.0, confidence)
    
    def clear_history(self, selection_id: Optional[int] = None):
        """Pulisce storia tick."""
        with self._lock:
            if selection_id:
                if selection_id in self._histories:
                    self._histories[selection_id].clear()
            else:
                self._histories.clear()
    
    def get_stats(self) -> Dict:
        """Ritorna statistiche engine."""
        with self._lock:
            total_ticks = sum(len(h.ticks) for h in self._histories.values())
            return {
                "selections_tracked": len(self._histories),
                "total_ticks": total_ticks,
                "window_size": self._window_size,
                "time_window": self._time_window
            }
    
    # ========== v3.67 Time-Window Analysis ==========
    
    def calculate_wom_window(self, selection_id: int, window_sec: float) -> float:
        """
        Calcola WoM per una specifica finestra temporale.
        
        Args:
            selection_id: ID runner
            window_sec: Finestra in secondi
            
        Returns:
            WoM ratio [0, 1], 0.5 se dati insufficienti
        """
        with self._lock:
            if selection_id not in self._histories:
                return 0.5
            
            ticks = self._histories[selection_id].get_recent(window_sec)
            if len(ticks) < 2:
                return 0.5
            
            total_back = sum(t.back_volume for t in ticks)
            total_lay = sum(t.lay_volume for t in ticks)
            total = total_back + total_lay
            
            return total_back / total if total > 0 else 0.5
    
    def calculate_multi_window_wom(self, selection_id: int) -> Dict[str, float]:
        """
        Calcola WoM su multiple finestre temporali.
        Operazione atomica con snapshot dei tick.
        
        Returns:
            Dict con wom_5s, wom_15s, wom_30s, wom_60s
        """
        with self._lock:
            if selection_id not in self._histories:
                return {"wom_5s": 0.5, "wom_15s": 0.5, "wom_30s": 0.5, "wom_60s": 0.5}
            
            all_ticks = list(self._histories[selection_id].ticks)
            now = time.time()
            
            def calc_wom_from_snapshot(ticks_list, window_sec):
                recent = [t for t in ticks_list if now - t.timestamp <= window_sec]
                if len(recent) < 2:
                    return 0.5
                total_back = sum(t.back_volume for t in recent)
                total_lay = sum(t.lay_volume for t in recent)
                total = total_back + total_lay
                return total_back / total if total > 0 else 0.5
            
            return {
                "wom_5s": calc_wom_from_snapshot(all_ticks, 5.0),
                "wom_15s": calc_wom_from_snapshot(all_ticks, 15.0),
                "wom_30s": calc_wom_from_snapshot(all_ticks, 30.0),
                "wom_60s": calc_wom_from_snapshot(all_ticks, 60.0)
            }
    
    def calculate_delta_pressure(self, selection_id: int) -> float:
        """
        Calcola il delta di pressione (cambiamento nel tempo).
        
        Confronta WoM recente (5s) vs storico (30s) per rilevare
        cambiamenti di momentum nel mercato.
        
        Returns:
            Delta [-1, 1]: positivo = pressione BACK aumenta
        """
        wom_5s = self.calculate_wom_window(selection_id, 5.0)
        wom_30s = self.calculate_wom_window(selection_id, 30.0)
        
        delta = wom_5s - wom_30s
        return max(-1.0, min(1.0, delta * 2))  # Amplifica per sensibilità
    
    def calculate_momentum(self, selection_id: int) -> float:
        """
        Calcola il momentum (velocità del cambiamento).
        
        Usa la derivata del WoM nel tempo per misurare
        quanto rapidamente sta cambiando la pressione.
        
        Returns:
            Momentum [-1, 1]: positivo = accelerazione BACK
        """
        with self._lock:
            if selection_id not in self._histories:
                return 0.0
            
            ticks = self._histories[selection_id].get_recent(30.0)
            if len(ticks) < 4:
                return 0.0
            
            # Dividi in quartili e calcola WoM per ciascuno
            q_size = len(ticks) // 4
            if q_size < 1:
                return 0.0
            
            quarters = [ticks[i*q_size:(i+1)*q_size] for i in range(4)]
            wom_values = []
            
            for q in quarters:
                if not q:
                    continue
                back = sum(t.back_volume for t in q)
                lay = sum(t.lay_volume for t in q)
                total = back + lay
                wom_values.append(back / total if total > 0 else 0.5)
            
            if len(wom_values) < 2:
                return 0.0
            
            # Calcola accelerazione (seconda derivata approssimata)
            deltas = [wom_values[i+1] - wom_values[i] for i in range(len(wom_values)-1)]
            momentum = sum(deltas) / len(deltas) if deltas else 0.0
            
            return max(-1.0, min(1.0, momentum * 4))
    
    def calculate_volatility(self, selection_id: int) -> float:
        """
        Calcola la volatilità del prezzo.
        
        Returns:
            Volatility [0, 1]: alto = mercato volatile
        """
        with self._lock:
            if selection_id not in self._histories:
                return 0.0
            
            ticks = self._histories[selection_id].get_recent(30.0)
            if len(ticks) < 3:
                return 0.0
            
            # Calcola spread medio e deviazione
            spreads = []
            for t in ticks:
                if t.lay_price > 0 and t.back_price > 0:
                    spreads.append(t.lay_price - t.back_price)
            
            if len(spreads) < 2:
                return 0.0
            
            avg_spread = sum(spreads) / len(spreads)
            variance = sum((s - avg_spread) ** 2 for s in spreads) / len(spreads)
            std_dev = variance ** 0.5
            
            # Normalizza (spread tipico 0.01-0.10)
            volatility = min(1.0, std_dev / 0.05)
            return volatility
    
    def calculate_enhanced_wom(self, selection_id: int) -> Optional[WoMResult]:
        """
        Calcola WoM completo con tutti i nuovi indicatori.
        
        Include:
        - WoM su multiple finestre (5s, 15s, 30s, 60s)
        - Delta pressure (cambio momentum)
        - Momentum (accelerazione)
        - Volatility (stabilità mercato)
        
        Returns:
            WoMResult completo con tutti gli indicatori
        """
        base_result = self.calculate_wom(selection_id)
        if not base_result:
            return None
        
        # Calcola indicatori avanzati
        multi_wom = self.calculate_multi_window_wom(selection_id)
        delta_pressure = self.calculate_delta_pressure(selection_id)
        momentum = self.calculate_momentum(selection_id)
        volatility = self.calculate_volatility(selection_id)
        
        # Crea risultato esteso
        return WoMResult(
            selection_id=base_result.selection_id,
            wom=base_result.wom,
            wom_trend=base_result.wom_trend,
            edge_score=base_result.edge_score,
            suggested_side=base_result.suggested_side,
            confidence=base_result.confidence,
            tick_count=base_result.tick_count,
            time_span=base_result.time_span,
            wom_5s=multi_wom["wom_5s"],
            wom_15s=multi_wom["wom_15s"],
            wom_30s=multi_wom["wom_30s"],
            wom_60s=multi_wom["wom_60s"],
            delta_pressure=delta_pressure,
            momentum=momentum,
            volatility=volatility
        )
    
    def get_time_window_signal(self, selection_id: int) -> Dict:
        """
        Genera segnale di trading basato su analisi time-window.
        
        Combina tutti gli indicatori per dare un segnale chiaro.
        
        Returns:
            Dict con signal, strength, reasoning
        """
        result = self.calculate_enhanced_wom(selection_id)
        if not result:
            return {
                "signal": "NO_DATA",
                "strength": 0.0,
                "side": "NEUTRAL",
                "reasoning": "Dati insufficienti"
            }
        
        # Analisi multi-timeframe
        short_term = result.wom_5s
        long_term = result.wom_30s
        
        # Convergenza: breve e lungo termine concordano
        convergence = abs(short_term - 0.5) * abs(long_term - 0.5) * 4
        
        # Segnale basato su delta + momentum
        signal_strength = (
            abs(result.delta_pressure) * 0.4 +
            abs(result.momentum) * 0.3 +
            abs(result.wom - 0.5) * 0.3
        )
        
        # Determina direzione
        if result.delta_pressure > DELTA_THRESHOLD and result.momentum > 0:
            signal = "STRONG_BACK"
            side = "BACK"
            reasoning = f"Pressione BACK in aumento (delta={result.delta_pressure:.2f})"
        elif result.delta_pressure < -DELTA_THRESHOLD and result.momentum < 0:
            signal = "STRONG_LAY"
            side = "LAY"
            reasoning = f"Pressione LAY in aumento (delta={result.delta_pressure:.2f})"
        elif result.wom > EDGE_THRESHOLDS["back"]:
            signal = "BACK"
            side = "BACK"
            reasoning = f"WoM favorisce BACK ({result.wom:.2f})"
        elif result.wom < EDGE_THRESHOLDS["lay"]:
            signal = "LAY"
            side = "LAY"
            reasoning = f"WoM favorisce LAY ({result.wom:.2f})"
        else:
            signal = "NEUTRAL"
            side = "NEUTRAL"
            reasoning = "Mercato in equilibrio"
        
        # Avviso volatilità
        if result.volatility > 0.7:
            reasoning += " [ALTA VOLATILITA']"
            signal_strength *= 0.8  # Riduci confidence su mercati volatili
        
        return {
            "signal": signal,
            "strength": min(1.0, signal_strength * convergence),
            "side": side,
            "reasoning": reasoning,
            "wom_data": {
                "wom_5s": result.wom_5s,
                "wom_15s": result.wom_15s,
                "wom_30s": result.wom_30s,
                "delta": result.delta_pressure,
                "momentum": result.momentum,
                "volatility": result.volatility
            }
        }


_global_wom_engine: Optional[WoMEngine] = None


def get_wom_engine() -> WoMEngine:
    """Ritorna istanza globale WoM Engine."""
    global _global_wom_engine
    if _global_wom_engine is None:
        _global_wom_engine = WoMEngine()
    return _global_wom_engine
