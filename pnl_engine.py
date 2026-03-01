"""
PnL Engine - Calcolo P&L live per selezione

Questo modulo calcola il profitto/perdita in tempo reale per ogni selezione,
utilizzando le quote live e la formula di cashout dinamico.
"""

import logging
from typing import Dict, Optional
from dutching import dynamic_cashout_single

logger = logging.getLogger(__name__)


class PnLEngine:
    """Engine per calcolo P&L live per selezione."""
    
    def __init__(self, commission: float = 4.5):
        """
        Args:
            commission: Commissione Betfair (default 4.5% Italia)
        """
        self.commission = commission
    
    def calculate_back_pnl(self, order: Dict, best_lay_price: float) -> float:
        """
        Calcola P&L live per una posizione BACK.
        
        Args:
            order: Dict con 'side', 'stake'/'sizeMatched', 'price'/'averagePriceMatched'
            best_lay_price: Miglior quota LAY live
            
        Returns:
            P&L netto arrotondato a 2 decimali
        """
        if order.get('side') != 'BACK':
            return 0.0
        
        stake = order.get('sizeMatched', order.get('stake', 0))
        price = order.get('averagePriceMatched', order.get('price', 0))
        
        if stake <= 0 or price <= 1 or best_lay_price <= 1:
            return 0.0
        
        try:
            result = dynamic_cashout_single(
                back_stake=stake,
                back_price=price,
                lay_price=best_lay_price,
                commission=self.commission
            )
            return round(result.get('net_profit', 0), 2)
        except Exception as e:
            logger.error(f"Errore calcolo P&L BACK: {e}")
            return 0.0
    
    def calculate_lay_pnl(self, order: Dict, best_back_price: float) -> float:
        """
        Calcola P&L live per una posizione LAY.
        
        Args:
            order: Dict con 'side', 'stake'/'sizeMatched', 'price'/'averagePriceMatched'
            best_back_price: Miglior quota BACK live
            
        Returns:
            P&L netto arrotondato a 2 decimali
        """
        if order.get('side') != 'LAY':
            return 0.0
        
        stake = order.get('sizeMatched', order.get('stake', 0))
        price = order.get('averagePriceMatched', order.get('price', 0))
        
        if stake <= 0 or price <= 1 or best_back_price <= 1:
            return 0.0
        
        try:
            liability = stake * (price - 1)
            
            if best_back_price >= price:
                profit = stake - (stake * price / best_back_price)
            else:
                profit = -(stake * price / best_back_price - stake)
            
            commission_mult = 1 - (self.commission / 100.0)
            net_profit = profit * commission_mult if profit > 0 else profit
            
            return round(net_profit, 2)
        except Exception as e:
            logger.error(f"Errore calcolo P&L LAY: {e}")
            return 0.0
    
    def calculate_order_pnl(self, order: Dict, best_back: float, best_lay: float) -> float:
        """
        Calcola P&L per qualsiasi ordine (BACK o LAY).
        
        Args:
            order: Ordine con side, stake, price
            best_back: Miglior BACK live
            best_lay: Miglior LAY live
            
        Returns:
            P&L netto
        """
        side = order.get('side', '')
        
        if side == 'BACK':
            return self.calculate_back_pnl(order, best_lay)
        elif side == 'LAY':
            return self.calculate_lay_pnl(order, best_back)
        
        return 0.0
    
    def calculate_selection_pnl(self, orders: list, best_back: float, best_lay: float) -> float:
        """
        Calcola P&L totale per una selezione (somma tutti gli ordini matched).
        
        Args:
            orders: Lista di ordini per la selezione
            best_back: Miglior BACK live
            best_lay: Miglior LAY live
            
        Returns:
            P&L totale per la selezione
        """
        total_pnl = 0.0
        for order in orders:
            total_pnl += self.calculate_order_pnl(order, best_back, best_lay)
        return round(total_pnl, 2)
    
    @staticmethod
    def is_auto_green_eligible(order: Dict, current_time: Optional[float] = None) -> bool:
        """
        Verifica se un ordine è idoneo per auto-green.
        
        Requisiti:
        - Ordine ha flag auto_green=True
        - Non è in modalità simulazione
        - È passato il grace period (AUTO_GREEN_DELAY_SEC)
        
        Args:
            order: Dict con metadata ordine
            current_time: Timestamp corrente (default: time.time())
            
        Returns:
            True se l'ordine può essere auto-greened
        """
        import time
        from trading_config import AUTO_GREEN_DELAY_SEC
        
        if not order.get('auto_green', False):
            return False
        
        if order.get('simulation', False):
            return False
        
        placed_at = order.get('placed_at', 0)
        if not placed_at:
            return False
        
        now = current_time or time.time()
        elapsed = now - placed_at
        
        if elapsed < AUTO_GREEN_DELAY_SEC:
            logger.debug(f"Auto-green: {elapsed:.1f}s < {AUTO_GREEN_DELAY_SEC}s grace period")
            return False
        
        return True
    
    def calculate_preview(self, selection: Dict, side: str = 'BACK') -> float:
        """
        Calcola P&L preview per un singolo runner (prima del piazzamento).
        
        Utile per MiniLadder preview.
        
        Args:
            selection: Dict con stake, price
            side: 'BACK' o 'LAY'
            
        Returns:
            P&L stimato
        """
        stake = selection.get('stake', selection.get('presetStake', 5.0))
        price = selection.get('price', 2.0)
        commission_pct = self.commission / 100.0
        
        if price <= 1:
            return 0.0
        
        if side == 'BACK':
            gross_profit = stake * (price - 1)
            net_profit = gross_profit * (1 - commission_pct)
        else:
            liability = stake * (price - 1)
            net_profit = stake * (1 - commission_pct) - liability * commission_pct
        
        return round(net_profit, 2)
