"""
Simulation Broker - Broker simulato per testing senza ordini reali

Fornisce stessa interfaccia di Betfair API per ordini, ma salva tutto in memoria.
Permette di testare strategie complete senza rischiare soldi reali.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Importa costanti da modulo config centralizzato
from trading_config import BOOK_WARNING, BOOK_BLOCK, MIN_STAKE, SIM_INITIAL_BALANCE


def apply_slippage(price_ladder: List[Dict], requested_size: float, 
                   side: str = 'BACK') -> tuple:
    """
    Applica slippage realistico basato sulla profondità del book.
    
    Quando la liquidità a un prezzo non basta, parte dello stake
    viene matchata a prezzi peggiori (simulazione exchange reale).
    
    Args:
        price_ladder: Lista di {'price': float, 'size': float} ordinata
                      Per BACK: dal prezzo più alto al più basso
                      Per LAY: dal prezzo più basso al più alto
        requested_size: Size richiesta
        side: 'BACK' o 'LAY'
        
    Returns:
        (matched_fills: List[Dict], remaining: float, avg_price: float)
        matched_fills: [{'price': float, 'size': float}, ...]
        remaining: size non matchata
        avg_price: prezzo medio ponderato
    """
    if not price_ladder:
        return [], requested_size, 0.0
    
    matched_fills = []
    remaining = requested_size
    total_value = 0.0
    total_matched = 0.0
    
    for level in price_ladder:
        if remaining <= 0:
            break
        
        price = level.get('price', 0)
        liquidity = level.get('size', 0)
        
        if price <= 0 or liquidity <= 0:
            continue
        
        taken = min(liquidity, remaining)
        matched_fills.append({'price': price, 'size': taken})
        
        total_value += taken * price
        total_matched += taken
        remaining -= taken
    
    avg_price = total_value / total_matched if total_matched > 0 else 0.0
    
    return matched_fills, remaining, avg_price


@dataclass
class SimulatedOrder:
    """Ordine simulato."""
    bet_id: str
    market_id: str
    selection_id: int
    runner_name: str
    side: str
    price: float  # Prezzo effettivo (medio se slippage)
    size: float
    matched: float = 0.0
    status: str = 'PENDING'
    placed_at: float = field(default_factory=time.time)
    price_requested: Optional[float] = None  # Prezzo originale richiesto
    
    def __post_init__(self):
        if self.price_requested is None:
            self.price_requested = self.price
    
    @property
    def size_matched(self) -> float:
        return self.matched
    
    @property
    def size_remaining(self) -> float:
        return self.size - self.matched


class SimulationBroker:
    """
    Broker simulato con stessa interfaccia di Betfair.
    
    Caratteristiche:
    - place_order() salva in memoria invece di inviare a Betfair
    - cancel_order() rimuove ordini pending
    - list_bets() ritorna tutti gli ordini
    - Simula matching automatico per ordini a prezzo di mercato
    """
    
    def __init__(self, initial_balance: Optional[float] = None, 
                 commission: float = 4.5):
        """
        Args:
            initial_balance: Bilancio iniziale simulato (default SIM_INITIAL_BALANCE)
            commission: Commissione su vincite (default 4.5%)
        """
        actual_balance = initial_balance if initial_balance is not None else SIM_INITIAL_BALANCE
        self.balance = actual_balance
        self.initial_balance = actual_balance
        self.commission = commission
        
        self.orders: Dict[str, SimulatedOrder] = {}
        self.bet_counter = 0
        self.lock = threading.RLock()
        
        logger.info(f"[SIM BROKER] Inizializzato con balance €{actual_balance:.2f}")
    
    def place_order(self, market_id: str, selection_id: int, side: str, 
                    price: float, size: float, runner_name: str = '',
                    price_ladder: Optional[List[Dict]] = None,
                    partial_match_pct: float = 1.0) -> Dict:
        """
        Piazza ordine simulato con supporto per matching parziale.
        
        Args:
            market_id: ID mercato
            selection_id: ID selezione
            side: 'BACK' o 'LAY'
            price: Quota
            size: Importo
            runner_name: Nome runner (opzionale)
            price_ladder: Profondità book per slippage (opzionale)
            partial_match_pct: Percentuale matching 0.0-1.0 (default 1.0 = full)
            
        Returns:
            Dict con dettagli ordine incluso bet_id
        """
        with self.lock:
            self.bet_counter += 1
            bet_id = f"SIM-{self.bet_counter:06d}"
            
            # Se price_ladder fornito, applica slippage
            if price_ladder:
                fills, remaining, avg_price = apply_slippage(price_ladder, size, side)
                matched_size = size - remaining
                final_price = avg_price if avg_price > 0 else price
            else:
                # Matching parziale basato su partial_match_pct
                matched_size = size * partial_match_pct
                remaining = size - matched_size
                final_price = price
                fills = [{'price': price, 'size': matched_size}] if matched_size > 0 else []
            
            # Determina status
            if matched_size >= size:
                status = 'EXECUTION_COMPLETE'
            elif matched_size > 0:
                status = 'EXECUTABLE'  # Parzialmente matchato
            else:
                status = 'EXECUTABLE'  # Tutto in attesa
            
            order = SimulatedOrder(
                bet_id=bet_id,
                market_id=market_id,
                selection_id=selection_id,
                runner_name=runner_name,
                side=side,
                price=final_price,
                size=size,
                matched=matched_size,
                status=status,
                price_requested=price  # Salva prezzo originale richiesto
            )
            
            self.orders[bet_id] = order
            
            # Riserva l'INTERA stake/liability (Betfair blocca tutto al placement)
            # Per LAY: matched usa prezzo effettivo, unmatched usa prezzo richiesto
            if side == 'BACK':
                self.balance -= size  # Riserva tutto
            else:
                # LAY: calcola liability separatamente per matched e unmatched
                matched_liability = matched_size * (final_price - 1)
                unmatched_liability = remaining * (price - 1)  # Usa prezzo richiesto!
                total_liability = matched_liability + unmatched_liability
                self.balance -= total_liability
            
            logger.info(f"[SIM] {side} €{matched_size:.2f}/{size:.2f} @ {final_price:.2f} su {runner_name} -> {bet_id}")
            
            return {
                'betId': bet_id,
                'selectionId': selection_id,
                'side': side,
                'price': final_price,
                'priceRequested': price,
                'size': size,
                'sizeMatched': matched_size,
                'sizeRemaining': remaining,
                'status': status,
                'fills': fills,
                'simulation': True
            }
    
    def place_order_with_slippage(self, market_id: str, selection_id: int, side: str,
                                   price: float, size: float, price_ladder: List[Dict],
                                   runner_name: str = '') -> Dict:
        """
        DEPRECATED: Usa place_order(price_ladder=...) invece.
        
        Wrapper per retrocompatibilità che chiama place_order con price_ladder.
        """
        return self.place_order(
            market_id=market_id,
            selection_id=selection_id,
            side=side,
            price=price,
            size=size,
            runner_name=runner_name,
            price_ladder=price_ladder
        )
    
    def cancel_order(self, bet_id: str) -> Dict:
        """
        Cancella ordine - gestisce correttamente ordini parzialmente matched.
        
        Comportamento Betfair-like:
        - Se matched_size == 0: cancella tutto, status = CANCELLED
        - Se matched_size > 0 e remaining > 0: cancella solo remaining, 
          matched resta attivo, status = EXECUTION_COMPLETE
        - Se già EXECUTION_COMPLETE: nulla da cancellare
        
        Returns:
            Dict con risultato: {'success': bool, 'sizeCancelled': float, 'sizeMatched': float}
        """
        with self.lock:
            order = self.orders.get(bet_id)
            if not order:
                return {'success': False, 'sizeCancelled': 0, 'sizeMatched': 0, 'error': 'NOT_FOUND'}
            
            # Caso 1: già completamente matchato o già cancellato
            if order.status in ('EXECUTION_COMPLETE', 'CANCELLED', 'SETTLED'):
                return {
                    'success': False, 
                    'sizeCancelled': 0, 
                    'sizeMatched': order.matched,
                    'error': 'NOTHING_TO_CANCEL'
                }
            
            size_to_cancel = order.size_remaining
            
            # Caso 2: completamente non matchato
            if order.matched == 0:
                order.status = 'CANCELLED'
                # Restituisci stake/liability al balance (usa price_requested per LAY)
                if order.side == 'BACK':
                    self.balance += size_to_cancel
                else:
                    # Usa prezzo richiesto per la liability (come era stata riservata)
                    liability = size_to_cancel * (order.price_requested - 1)
                    self.balance += liability
                
                logger.info(f"[SIM] Ordine {bet_id} cancellato completamente (size={size_to_cancel:.2f})")
                return {'success': True, 'sizeCancelled': size_to_cancel, 'sizeMatched': 0}
            
            # Caso 3: parzialmente matchato - cancella solo remaining
            if order.matched > 0 and order.size_remaining > 0:
                # Restituisci solo la parte non matchata (usa price_requested per LAY)
                if order.side == 'BACK':
                    self.balance += size_to_cancel
                else:
                    # Usa prezzo richiesto per la liability unmatched
                    liability = size_to_cancel * (order.price_requested - 1)
                    self.balance += liability
                
                # Aggiorna ordine: size diventa solo matched, status EXECUTION_COMPLETE
                order.size = order.matched
                order.status = 'EXECUTION_COMPLETE'
                
                logger.info(f"[SIM] Ordine {bet_id} parziale: cancellato €{size_to_cancel:.2f}, matched €{order.matched:.2f} resta attivo")
                return {
                    'success': True, 
                    'sizeCancelled': size_to_cancel, 
                    'sizeMatched': order.matched
                }
            
            return {'success': False, 'sizeCancelled': 0, 'sizeMatched': order.matched}
    
    def list_bets(self, market_id: Optional[str] = None, 
                  status: Optional[str] = None) -> List[Dict]:
        """
        Lista ordini simulati.
        
        Args:
            market_id: Filtra per mercato
            status: Filtra per status ('MATCHED', 'PENDING', 'CANCELLED')
            
        Returns:
            Lista di dict ordini
        """
        with self.lock:
            result = []
            for order in self.orders.values():
                if market_id and order.market_id != market_id:
                    continue
                if status and order.status != status:
                    continue
                
                result.append({
                    'betId': order.bet_id,
                    'marketId': order.market_id,
                    'selectionId': order.selection_id,
                    'runnerName': order.runner_name,
                    'side': order.side,
                    'price': order.price,
                    'size': order.size,
                    'sizeMatched': order.matched,
                    'status': order.status,
                    'placedAt': order.placed_at,
                    'simulation': True
                })
            
            return result
    
    def get_order(self, bet_id: str) -> Optional[Dict]:
        """Ritorna singolo ordine."""
        with self.lock:
            order = self.orders.get(bet_id)
            if not order:
                return None
            
            return {
                'betId': order.bet_id,
                'marketId': order.market_id,
                'selectionId': order.selection_id,
                'runnerName': order.runner_name,
                'side': order.side,
                'price': order.price,
                'size': order.size,
                'sizeMatched': order.matched,
                'status': order.status,
                'simulation': True
            }
    
    def get_balance(self) -> float:
        """Ritorna bilancio attuale."""
        return self.balance
    
    def get_pnl(self) -> float:
        """Ritorna P&L rispetto a bilancio iniziale."""
        return self.balance - self.initial_balance
    
    def reset(self):
        """Reset completo del broker."""
        with self.lock:
            self.orders.clear()
            self.bet_counter = 0
            self.balance = self.initial_balance
            logger.info("[SIM] Broker resettato")
    
    def settle_market(self, market_id: str, winner_selection_id: int) -> float:
        """
        Regola mercato con vincitore noto.
        
        Rilascia anche la liability bloccata per ordini non matchati.
        
        Args:
            market_id: ID mercato
            winner_selection_id: ID della selezione vincente
            
        Returns:
            P&L totale per il mercato
        """
        with self.lock:
            pnl = 0.0
            
            for order in self.orders.values():
                if order.market_id != market_id:
                    continue
                # Skip ordini già regolati o cancellati
                if order.status in ('SETTLED', 'CANCELLED'):
                    continue
                
                # Rilascia sempre la parte non matchata (era stata riservata al placement)
                unmatched = order.size - order.matched
                if unmatched > 0:
                    if order.side == 'BACK':
                        self.balance += unmatched
                    else:
                        # Usa prezzo richiesto per la liability unmatched (come era stata riservata)
                        unmatched_liability = unmatched * (order.price_requested - 1)
                        self.balance += unmatched_liability
                    logger.debug(f"[SIM] Rilasciata exposure non matchata €{unmatched:.2f} per {order.bet_id}")
                
                # Se nessun match, solo rilascio exposure
                if order.matched <= 0:
                    order.status = 'SETTLED'
                    continue
                
                won = (order.selection_id == winner_selection_id)
                
                if order.side == 'BACK':
                    if won:
                        # BACK vinto: restituisci stake matchata + profitto netto
                        gross = order.matched * (order.price - 1)
                        net = gross * (1 - self.commission / 100)
                        pnl += net
                        self.balance += order.matched + net
                    else:
                        # BACK perso: stake era già stata sottratta, nulla da restituire
                        pnl -= order.matched
                else:  # LAY
                    if won:
                        # LAY perso (selezione ha vinto): perdiamo la liability
                        liability = order.matched * (order.price - 1)
                        pnl -= liability
                        # La liability era già sottratta, nulla da fare
                    else:
                        # LAY vinto (selezione ha perso): vinciamo stake netta + restituiamo liability
                        gross = order.matched
                        net = gross * (1 - self.commission / 100)
                        pnl += net
                        liability = order.matched * (order.price - 1)
                        self.balance += liability + net
                
                order.status = 'SETTLED'
            
            logger.info(f"[SIM] Mercato {market_id} regolato, P&L: €{pnl:.2f}")
            return pnl


class BookOptimizer:
    """
    Ottimizzatore Book % per dutching.
    
    Quando book > warning_threshold, redistribuisce stake proporzionalmente
    per mantenere book entro limiti sicuri.
    Rispetta stake minimo €2 (Betfair Italia).
    """
    
    def __init__(self, warning_threshold: Optional[float] = None, 
                 max_threshold: Optional[float] = None,
                 min_stake: Optional[float] = None):
        """
        Args:
            warning_threshold: Soglia warning book % (default BOOK_WARNING)
            max_threshold: Soglia blocco submit (default BOOK_BLOCK)
            min_stake: Stake minimo per ordine (default MIN_STAKE = 2.0€)
        """
        self.warning_threshold = warning_threshold or BOOK_WARNING
        self.max_threshold = max_threshold or BOOK_BLOCK
        self.min_stake = min_stake or MIN_STAKE
    
    def calculate_book(self, selections: List[Dict]) -> float:
        """
        Calcola book % dalle selezioni.
        
        Args:
            selections: Lista con 'price' per ogni runner
            
        Returns:
            Book % (100 = fair, >100 = overround)
        """
        if not selections:
            return 0.0
        
        total = sum(1 / s['price'] for s in selections if s.get('price', 0) > 1)
        return total * 100
    
    def optimize(self, selections: List[Dict], target_book: float = 100.0) -> List[Dict]:
        """
        Ottimizza stake per raggiungere target book % con equal-profit.
        
        Rispetta min_stake: se uno stake scende sotto €2, viene
        fissato a min_stake e gli altri vengono ribilanciati per
        mantenere distribuzione equal-profit.
        
        Args:
            selections: Lista selezioni con 'stake' e 'price'
            target_book: Book % target
            
        Returns:
            Selezioni con stake ottimizzati
        """
        current_book = self.calculate_book(selections)
        
        if current_book <= target_book:
            return selections
        
        # Copia per non modificare originali
        result = [dict(s) for s in selections]
        
        # Calcola total stake corrente
        total_stake = sum(s.get('stake', 0) for s in result)
        if total_stake <= 0:
            return result
        
        # Iterazione: clamp e ribilancia fino a convergenza
        max_iterations = 10
        for iteration in range(max_iterations):
            # Calcola profitto target (equal profit dutching)
            # profit = total_stake / book - total_stake
            book_pct = self.calculate_book(result)
            if book_pct <= 0:
                break
                
            # Stake proporzionale alle probabilità inverse
            unclamped = [s for s in result if not s.get('clamped', False)]
            clamped = [s for s in result if s.get('clamped', False)]
            
            # Calcola stake disponibile dopo stake fissati
            clamped_stake = sum(s.get('stake', 0) for s in clamped)
            available_stake = total_stake - clamped_stake
            
            if not unclamped or available_stake <= 0:
                break
            
            # Calcola probabilità per selezioni non clampate
            unclamped_prob_sum = sum(1 / s['price'] for s in unclamped if s.get('price', 0) > 1)
            
            if unclamped_prob_sum <= 0:
                break
            
            # Distribuisci stake rimanente proporzionalmente
            needs_rebalance = False
            for s in unclamped:
                if s.get('price', 0) > 1:
                    prob = 1 / s['price']
                    new_stake = (prob / unclamped_prob_sum) * available_stake
                    
                    if new_stake < self.min_stake:
                        s['stake'] = self.min_stake
                        s['clamped'] = True
                        needs_rebalance = True
                    else:
                        s['stake'] = round(new_stake, 2)
            
            if not needs_rebalance:
                break
        
        final_book = self.calculate_book(result)
        logger.info(f"[BOOK OPT] Ribilanciato: {current_book:.1f}% -> {final_book:.1f}% (target {target_book:.1f}%)")
        return result
    
    def get_status(self, book_value: float) -> str:
        """
        Ritorna status per UI.
        
        Returns:
            'OK', 'WARNING', o 'BLOCKED'
        """
        if book_value > self.max_threshold:
            return 'BLOCKED'
        elif book_value > self.warning_threshold:
            return 'WARNING'
        return 'OK'
    
    def validate_stakes(self, selections: List[Dict]) -> List[str]:
        """
        Valida che tutti gli stake siano >= min_stake.
        
        Returns:
            Lista di errori (vuota se tutto ok)
        """
        errors = []
        for s in selections:
            stake = s.get('stake', 0)
            if 0 < stake < self.min_stake:
                errors.append(f"{s.get('runnerName', 'Runner')}: €{stake:.2f} < min €{self.min_stake:.2f}")
        return errors


class TickReplayEngine:
    """
    Engine per replay storico tick.
    
    Permette di riprodurre tick passati per testare strategie
    senza rischio, con velocità configurabile.
    """
    
    def __init__(self, on_tick: Optional[Callable] = None):
        """
        Args:
            on_tick: Callback chiamato per ogni tick (selection_id, price)
        """
        self.ticks: List[Dict] = []
        self.index = 0
        self.on_tick = on_tick
        self.playing = False
        self.speed = 1.0
        self.lock = threading.Lock()
    
    def load_ticks(self, ticks: List[Dict]):
        """
        Carica tick storici.
        
        Args:
            ticks: Lista di {'selectionId': int, 'price': float, 'timestamp': float}
        """
        with self.lock:
            self.ticks = sorted(ticks, key=lambda t: t.get('timestamp', 0))
            self.index = 0
            logger.info(f"[REPLAY] Caricati {len(ticks)} tick")
    
    def next_tick(self) -> Optional[Dict]:
        """Ritorna prossimo tick o None se finito."""
        with self.lock:
            if self.index >= len(self.ticks):
                return None
            
            tick = self.ticks[self.index]
            self.index += 1
            
            if self.on_tick:
                self.on_tick(tick['selectionId'], tick['price'])
            
            return tick
    
    def play(self, speed: float = 1.0):
        """
        Avvia replay automatico in background.
        
        Args:
            speed: Velocità (1.0 = tempo reale, 2.0 = doppia velocità)
        """
        self.speed = speed
        self.playing = True
        
        def _play_loop():
            while self.playing:
                tick = self.next_tick()
                if not tick:
                    self.playing = False
                    break
                time.sleep(1.0 / self.speed)
        
        thread = threading.Thread(target=_play_loop, daemon=True)
        thread.start()
        logger.info(f"[REPLAY] Avviato a velocità {speed}x")
    
    def pause(self):
        """Mette in pausa replay."""
        self.playing = False
    
    def reset(self):
        """Reset replay all'inizio."""
        with self.lock:
            self.index = 0
            self.playing = False
    
    @property
    def progress(self) -> float:
        """Ritorna progresso 0.0 - 1.0."""
        with self.lock:
            if not self.ticks:
                return 0.0
            return self.index / len(self.ticks)
