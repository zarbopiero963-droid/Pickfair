"""
Order Manager - Replace Intelligenti con Guard Rail.

Architettura:
    Live Odds -> Auto-Follow Engine -> Tick Ladder Normalize
    -> Anti-loop Protection -> Profit Threshold Check -> replaceOrders() -> fallback cancel+place

Features:
    - Tick ladder Betfair ufficiale
    - Anti-loop protection (rate limit + max replaces)
    - PROFIT THRESHOLD: replace solo se Δprofit > soglia
    - Auto-follow best price (BACK/LAY)
    - replaceOrders con fallback cancel+place
    - Tracking betId cambiati
    - Metriche: replace eseguiti/saltati
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TICK_LADDER = [
    (1.01, 2.0, 0.01),
    (2.0, 3.0, 0.02),
    (3.0, 4.0, 0.05),
    (4.0, 6.0, 0.1),
    (6.0, 10.0, 0.2),
    (10.0, 20.0, 0.5),
    (20.0, 30.0, 1.0),
    (30.0, 50.0, 2.0),
    (50.0, 100.0, 5.0),
    (100.0, 1000.0, 10.0),
]


def normalize_price(price: float) -> float:
    """Normalizza prezzo al tick Betfair valido piu vicino."""
    if price < 1.01:
        return 1.01
    if price >= 1000.0:
        return 1000.0
    
    for low, high, tick in TICK_LADDER:
        if low <= price < high:
            normalized = round(round(price / tick) * tick, 2)
            return max(low, min(normalized, high - tick))
    
    return round(price, 2)


def get_tick_size(price: float) -> float:
    """Restituisce il tick size per un dato prezzo."""
    for low, high, tick in TICK_LADDER:
        if low <= price < high:
            return tick
    return 0.01


def next_tick_up(price: float) -> float:
    """Prossimo tick superiore."""
    tick = get_tick_size(price)
    return normalize_price(price + tick)


def next_tick_down(price: float) -> float:
    """Prossimo tick inferiore."""
    tick = get_tick_size(price)
    return normalize_price(price - tick)


def ticks_difference(price1: float, price2: float) -> int:
    """Calcola quanti tick di differenza tra due prezzi."""
    if price1 == price2:
        return 0
    
    low, high = min(price1, price2), max(price1, price2)
    ticks = 0
    current = low
    
    while current < high:
        current = next_tick_up(current)
        ticks += 1
        if ticks > 1000:
            break
    
    return ticks if price1 < price2 else -ticks


def calculate_profit_delta(old_price: float, new_price: float, stake: float, side: str) -> float:
    """Calcola il delta profitto tra due prezzi."""
    if side == 'BACK':
        old_profit = stake * (old_price - 1)
        new_profit = stake * (new_price - 1)
        return new_profit - old_profit
    else:
        old_liability = stake * (old_price - 1)
        new_liability = stake * (new_price - 1)
        return old_liability - new_liability


class ReplaceGuard:
    """
    Protezione anti-loop per replaceOrders.
    
    Previene:
    - Spam di replace troppo frequenti
    - Loop infiniti di modifiche
    - Ban da rate limit Betfair
    """
    
    def __init__(self, min_interval: float = 0.4, max_replaces: int = 5, reset_after: float = 10.0):
        self.last_replace: Dict[str, float] = {}
        self.replace_count: Dict[str, int] = {}
        self.min_interval = min_interval
        self.max_replaces = max_replaces
        self.reset_after = reset_after
    
    def can_replace(self, bet_id: str) -> Tuple[bool, str]:
        """Verifica se e' possibile fare replace."""
        now = time.time()
        
        last = self.last_replace.get(bet_id, 0)
        count = self.replace_count.get(bet_id, 0)
        
        if now - last > self.reset_after:
            self.replace_count[bet_id] = 0
            count = 0
        
        if now - last < self.min_interval:
            return False, f"Rate limit ({self.min_interval}s)"
        
        if count >= self.max_replaces:
            return False, f"Max replaces ({self.max_replaces})"
        
        return True, "OK"
    
    def record_replace(self, bet_id: str):
        """Registra un replace effettuato."""
        now = time.time()
        self.last_replace[bet_id] = now
        self.replace_count[bet_id] = self.replace_count.get(bet_id, 0) + 1
    
    def reset(self, bet_id: str):
        """Reset contatori per un betId."""
        self.last_replace.pop(bet_id, None)
        self.replace_count.pop(bet_id, None)
    
    def reset_all(self):
        """Reset tutti i contatori."""
        self.last_replace.clear()
        self.replace_count.clear()
    
    def get_stats(self, bet_id: str) -> Dict:
        """Statistiche per un betId."""
        now = time.time()
        return {
            'betId': bet_id,
            'replaceCount': self.replace_count.get(bet_id, 0),
            'lastReplace': self.last_replace.get(bet_id, 0),
            'secondsSinceLast': now - self.last_replace.get(bet_id, 0),
            'canReplace': self.can_replace(bet_id)[0]
        }


class ReplaceMetrics:
    """Metriche replace eseguiti vs saltati."""
    
    def __init__(self):
        self.executed = 0
        self.skipped = 0
        self.skipped_profit_threshold = 0
        self.skipped_rate_limit = 0
        self.skipped_same_price = 0
        self.total_profit_delta = 0.0
        self._start_time = time.time()
    
    def record_executed(self, profit_delta: float = 0.0):
        self.executed += 1
        self.total_profit_delta += profit_delta
    
    def record_skipped(self, reason: str):
        self.skipped += 1
        if 'profit' in reason.lower() or 'threshold' in reason.lower():
            self.skipped_profit_threshold += 1
        elif 'rate' in reason.lower() or 'guard' in reason.lower():
            self.skipped_rate_limit += 1
        elif 'stesso' in reason.lower() or 'same' in reason.lower():
            self.skipped_same_price += 1
    
    def get_stats(self) -> Dict:
        total = self.executed + self.skipped
        return {
            'executed': self.executed,
            'skipped': self.skipped,
            'skipped_profit_threshold': self.skipped_profit_threshold,
            'skipped_rate_limit': self.skipped_rate_limit,
            'skipped_same_price': self.skipped_same_price,
            'execution_rate': round(self.executed / max(1, total) * 100, 1),
            'total_profit_delta': round(self.total_profit_delta, 2),
            'uptime_min': round((time.time() - self._start_time) / 60, 1)
        }
    
    def reset(self):
        self.executed = 0
        self.skipped = 0
        self.skipped_profit_threshold = 0
        self.skipped_rate_limit = 0
        self.skipped_same_price = 0
        self.total_profit_delta = 0.0
        self._start_time = time.time()


_replace_metrics = ReplaceMetrics()


def get_replace_metrics() -> ReplaceMetrics:
    return _replace_metrics


def should_replace(
    current_price: float,
    best_price: float,
    side: str,
    stake: float = 0,
    min_ticks: int = 1,
    profit_threshold: float = 0.1
) -> Tuple[bool, str, float]:
    """
    Determina se conviene fare replace per seguire best price.
    
    BACK -> segue miglior quota piu ALTA (vogliamo piu profitto)
    LAY  -> segue miglior quota piu BASSA (vogliamo meno liability)
    
    Returns:
        (should_replace, reason, profit_delta)
    """
    if current_price == best_price:
        return False, "Stesso prezzo", 0.0
    
    normalized_best = normalize_price(best_price)
    
    if current_price == normalized_best:
        return False, "Gia al best price normalizzato", 0.0
    
    ticks = abs(ticks_difference(current_price, normalized_best))
    
    if ticks < min_ticks:
        return False, f"Differenza < {min_ticks} tick", 0.0
    
    profit_delta = calculate_profit_delta(current_price, normalized_best, stake, side)
    
    if side == 'BACK':
        if normalized_best > current_price:
            if profit_delta < profit_threshold:
                return False, f"Profit delta {profit_delta:.2f} < threshold {profit_threshold}", profit_delta
            return True, f"BACK: +{ticks} tick, +{profit_delta:.2f}EUR", profit_delta
        else:
            return False, "BACK: nuova quota peggiore", profit_delta
    else:
        if normalized_best < current_price:
            if abs(profit_delta) < profit_threshold:
                return False, f"Liability delta {abs(profit_delta):.2f} < threshold {profit_threshold}", profit_delta
            return True, f"LAY: -{ticks} tick, +{abs(profit_delta):.2f}EUR liability saved", profit_delta
        else:
            return False, "LAY: nuova quota peggiore", profit_delta


class OrderManager:
    """
    Gestore ordini intelligente con auto-follow e replace.
    
    Features:
    - Auto-follow best price
    - PROFIT THRESHOLD: solo replace significativi
    - replaceOrders con tick ladder
    - Fallback cancel+place
    - Anti-loop protection
    - Tracking betId
    - Metriche performance
    - Thread-safe
    """
    
    def __init__(
        self, 
        betfair_client, 
        min_interval: float = 0.4, 
        max_replaces: int = 5,
        profit_threshold: float = 0.1
    ):
        self.client = betfair_client
        self.guard = ReplaceGuard(min_interval, max_replaces)
        self.bet_id_map: Dict[str, str] = {}
        self.order_history: List[Dict] = []
        self.profit_threshold = profit_threshold
        self.metrics = get_replace_metrics()
        self._lock = threading.RLock()
    
    def get_current_bet_id(self, original_bet_id: str) -> str:
        """Restituisce il betId attuale (potrebbe essere cambiato dopo replace)."""
        with self._lock:
            current = original_bet_id
            while current in self.bet_id_map:
                current = self.bet_id_map[current]
            return current
    
    def smart_update_order(
        self,
        bet_id: str,
        market_id: str,
        selection_id: int,
        side: str,
        current_price: float,
        best_price: float,
        size_remaining: float,
        min_ticks: int = 1
    ) -> Dict:
        """
        Aggiorna ordine intelligentemente per seguire best price.
        
        Flow:
        1. Normalizza prezzo al tick ladder
        2. Verifica se conviene replace (PROFIT THRESHOLD)
        3. Check anti-loop protection
        4. Try replaceOrders
        5. Fallback cancel+place se fallisce
        """
        result = {
            'success': False,
            'action': None,
            'originalBetId': bet_id,
            'newBetId': None,
            'newPrice': None,
            'reason': None,
            'profitDelta': 0.0
        }
        
        current_bet_id = self.get_current_bet_id(bet_id)
        normalized_price = normalize_price(best_price)
        result['newPrice'] = normalized_price
        
        should, reason, profit_delta = should_replace(
            current_price, normalized_price, side, 
            stake=size_remaining,
            min_ticks=min_ticks,
            profit_threshold=self.profit_threshold
        )
        result['profitDelta'] = profit_delta
        
        if not should:
            result['reason'] = reason
            self.metrics.record_skipped(reason)
            return result
        
        can, guard_reason = self.guard.can_replace(current_bet_id)
        if not can:
            result['reason'] = f"Guard: {guard_reason}"
            self.metrics.record_skipped(guard_reason)
            return result
        
        logger.info(f"[ORDER_MGR] {side} {current_bet_id}: {current_price} -> {normalized_price} ({reason})")
        
        try:
            response = self.client.replace_orders(
                market_id=market_id,
                bet_id=current_bet_id,
                new_price=normalized_price
            )
            
            if response.get('status') == 'SUCCESS':
                self.guard.record_replace(current_bet_id)
                self.metrics.record_executed(profit_delta)
                
                reports = response.get('instructionReports', [])
                if reports:
                    new_bet_id = reports[0].get('newBetId')
                    if new_bet_id and new_bet_id != current_bet_id:
                        with self._lock:
                            self.bet_id_map[current_bet_id] = new_bet_id
                        result['newBetId'] = new_bet_id
                        logger.info(f"[ORDER_MGR] BetId changed: {current_bet_id} -> {new_bet_id}")
                    else:
                        result['newBetId'] = current_bet_id
                
                result['success'] = True
                result['action'] = 'REPLACE'
                result['reason'] = 'SUCCESS'
                
                self._record_history('REPLACE', result)
                return result
            
            error_msg = response.get('status', 'UNKNOWN')
            logger.warning(f"[ORDER_MGR] Replace failed: {error_msg}")
            
        except Exception as e:
            logger.error(f"[ORDER_MGR] Replace exception: {e}")
        
        return self._fallback_cancel_place(
            market_id=market_id,
            selection_id=selection_id,
            side=side,
            price=normalized_price,
            size=size_remaining,
            original_bet_id=current_bet_id,
            profit_delta=profit_delta
        )
    
    def _fallback_cancel_place(
        self,
        market_id: str,
        selection_id: int,
        side: str,
        price: float,
        size: float,
        original_bet_id: str,
        profit_delta: float = 0.0
    ) -> Dict:
        """Fallback: cancella ordine e piazza nuovo."""
        result = {
            'success': False,
            'action': 'CANCEL_PLACE',
            'originalBetId': original_bet_id,
            'newBetId': None,
            'newPrice': price,
            'reason': None,
            'profitDelta': profit_delta
        }
        
        logger.info(f"[ORDER_MGR] Fallback cancel+place for {original_bet_id}")
        
        try:
            cancel_result = self.client.cancel_orders(market_id, [original_bet_id])
            
            if cancel_result.get('status') != 'SUCCESS':
                result['reason'] = f"Cancel failed: {cancel_result.get('status')}"
                self.metrics.record_skipped("cancel_failed")
                return result
            
            place_result = self.client.place_bet(
                market_id=market_id,
                selection_id=selection_id,
                side=side,
                price=price,
                size=round(size, 2)
            )
            
            if place_result.get('status') == 'SUCCESS':
                new_bet_id = place_result.get('betId')
                if new_bet_id:
                    with self._lock:
                        self.bet_id_map[original_bet_id] = new_bet_id
                    result['newBetId'] = new_bet_id
                
                result['success'] = True
                result['reason'] = 'FALLBACK_SUCCESS'
                
                self.guard.record_replace(original_bet_id)
                self.metrics.record_executed(profit_delta)
                self._record_history('CANCEL_PLACE', result)
                
                logger.info(f"[ORDER_MGR] Fallback success: {original_bet_id} -> {new_bet_id}")
            else:
                result['reason'] = f"Place failed: {place_result.get('status')}"
                self.metrics.record_skipped("place_failed")
            
        except Exception as e:
            result['reason'] = f"Fallback exception: {e}"
            self.metrics.record_skipped("fallback_exception")
            logger.error(f"[ORDER_MGR] Fallback error: {e}")
        
        return result
    
    def _record_history(self, action: str, result: Dict):
        """Registra operazione nella history."""
        self.order_history.append({
            'timestamp': time.time(),
            'action': action,
            **result
        })
        
        if len(self.order_history) > 100:
            self.order_history = self.order_history[-100:]
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """Ultimi N record della history."""
        return self.order_history[-limit:]
    
    def get_metrics(self) -> Dict:
        """Restituisce metriche replace."""
        return self.metrics.get_stats()
    
    def reset(self):
        """Reset completo del manager."""
        self.guard.reset_all()
        self.bet_id_map.clear()
        self.order_history.clear()


def batch_follow_orders(
    order_manager: OrderManager,
    orders: List[Dict],
    live_prices: Dict[int, Dict],
    min_ticks: int = 1
) -> List[Dict]:
    """
    Aggiorna batch di ordini per seguire best price.
    """
    results = []
    
    for order in orders:
        sel_id = order.get('selectionId')
        side = order.get('side', 'BACK')
        
        prices = live_prices.get(sel_id, {})
        best_price = prices.get('back' if side == 'BACK' else 'lay', order.get('price', 0))
        
        if not best_price:
            results.append({'success': False, 'reason': 'No live price'})
            continue
        
        result = order_manager.smart_update_order(
            bet_id=order.get('betId'),
            market_id=order.get('marketId'),
            selection_id=sel_id,
            side=side,
            current_price=order.get('price', 0),
            best_price=best_price,
            size_remaining=order.get('sizeRemaining', 0),
            min_ticks=min_ticks
        )
        results.append(result)
    
    return results
