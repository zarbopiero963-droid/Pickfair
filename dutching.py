"""
Dutching Engine per Betfair Exchange.
Calcolo stake ottimali per profitto uniforme su multiple selezioni.
Hedge-Fund Grade: Utilizza Decimal per precisione finanziaria assoluta.
"""

import logging
from typing import List, Dict, Tuple
from decimal import Decimal, ROUND_HALF_UP, getcontext

# Set precisione globale per i calcoli monetari
getcontext().prec = 12

logger = logging.getLogger(__name__)

# Costanti Betfair Italia
MIN_STAKE = Decimal("2.00")
STEP = Decimal("0.50")
MAX_WIN = Decimal("10000.00")

def round_step(value: Decimal) -> Decimal:
    """Arrotonda al multiplo di 0.50 (Step Betfair Italia)."""
    return (value / STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * STEP

def validate_selections(results: List[Dict], bet_type: str = "BACK") -> List[str]:
    """Valida selezioni per requisiti Betfair."""
    errors = []
    for r in results:
        stake = Decimal(str(r.get("stake", 0)))
        if stake < Decimal("1.00"): # Permettiamo 1.00 per simulazioni, ma il reale è 2.00
            errors.append(f"Stake troppo basso: {stake:.2f} EUR")
        
        win = Decimal(str(r.get("profit_if_win", r.get("profitIfWins", 0))))
        if win > MAX_WIN:
            errors.append(f"Vincita massima superata: {win:.2f} > {MAX_WIN}")
            
    return errors

def calculate_dutching_stakes(
    selections: List[Dict],
    total_stake: float,
    side: str = "BACK",
    commission: float = 4.5
) -> Tuple[List[Dict], float, float]:
    """
    Entry point principale per calcolo dutching usando Decimal.
    """
    if not selections:
        return [], 0.0, 0.0

    if side == "BACK":
        return _calculate_back_dutching(selections, total_stake, commission)
    else:
        return _calculate_lay_dutching(selections, total_stake, commission)

def _calculate_back_dutching(selections: List[Dict], total_stake: float, commission: float) -> Tuple[List[Dict], float, float]:
    total_stake_dec = Decimal(str(total_stake))
    comm_mult = Decimal("1") - (Decimal(str(commission)) / Decimal("100"))
    
    # Probabilità implicita usando Decimal
    implied_probs = []
    for sel in selections:
        price = Decimal(str(sel.get('price', 0)))
        if price <= Decimal("1.01"):
            raise ValueError("Quota non valida (<= 1.01)")
        implied_probs.append(Decimal("1") / price)
        
    book_value = sum(implied_probs)
    if book_value >= Decimal("1"):
        raise ValueError(f"Book value sfavorevole: {(book_value*100):.2f}%")

    results = []
    total_actual_stake = Decimal("0")
    
    # Calcolo proporzionale
    for i, sel in enumerate(selections):
        stake = (total_stake_dec * implied_probs[i]) / book_value
        stake = round_step(stake)
        
        if stake < MIN_STAKE:
            stake = MIN_STAKE
            
        total_actual_stake += stake
        
        price = Decimal(str(sel['price']))
        gross_return = stake * price
        net_profit = (gross_return - total_stake_dec) * comm_mult
        
        results.append({
            'selectionId': sel['selectionId'],
            'runnerName': sel.get('runnerName', str(sel['selectionId'])),
            'price': float(price),
            'stake': float(stake),
            'profitIfWins': float(net_profit)
        })

    avg_profit = sum(Decimal(str(r['profitIfWins'])) for r in results) / len(results)
    
    return results, float(avg_profit), float(book_value * 100)

def _calculate_lay_dutching(selections: List[Dict], total_target_profit: float, commission: float) -> Tuple[List[Dict], float, float]:
    target_profit_dec = Decimal(str(total_target_profit))
    
    implied_probs = []
    for sel in selections:
        price = Decimal(str(sel.get('price', 0)))
        if price <= Decimal("1.01"):
            raise ValueError("Quota non valida")
        implied_probs.append(Decimal("1") / price)
        
    book_value = sum(implied_probs)
    
    results = []
    worst_liability = Decimal("0")
    
    for i, sel in enumerate(selections):
        price = Decimal(str(sel['price']))
        stake = target_profit_dec  # Nel LAY dutching, lo stake = target profit
        stake = round_step(stake)
        
        liability = stake * (price - Decimal("1"))
        if liability > worst_liability:
            worst_liability = liability
            
        results.append({
            'selectionId': sel['selectionId'],
            'runnerName': sel.get('runnerName', str(sel['selectionId'])),
            'price': float(price),
            'stake': float(stake),
            'liability': float(liability),
            'profitIfWins': float(target_profit_dec) # Il profitto è netto se vince il banco
        })
        
    return results, float(target_profit_dec), float(book_value * 100)

def dynamic_cashout_single(matched_stake: float, matched_price: float, current_price: float, commission: float = 4.5) -> dict:
    """Cashout usando Decimal."""
    ms = Decimal(str(matched_stake))
    mp = Decimal(str(matched_price))
    cp = Decimal(str(current_price))
    
    if cp <= Decimal("1.01"):
        return {'lay_stake': 0.0, 'green_up': 0.0}
        
    # BACK cashout (piazzando LAY)
    cashout_stake = (ms * mp) / cp
    cashout_stake = cashout_stake.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    profit_win = ms * (mp - Decimal("1")) - cashout_stake * (cp - Decimal("1"))
    profit_lose = cashout_stake - ms
    
    green = (profit_win + profit_lose) / Decimal("2")
    
    return {
        'lay_stake': float(cashout_stake),
        'green_up': float(green)
    }

def calculate_mixed_dutching(selections: List[Dict], amount: float, commission: float = 4.5) -> Tuple[List[Dict], float, float]:
    """Fallback al dutching BACK standard."""
    return _calculate_back_dutching(selections, amount, commission)