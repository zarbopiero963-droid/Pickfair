"""
Dutching Engine per Betfair Exchange.
Calcolo stake ottimali per profitto uniforme su multiple selezioni.
Hedge-Fund Grade: Utilizza Decimal per precisione finanziaria assoluta.

Fix applicati:
- micro-stake abilitato a 0.10
- rounding al centesimo
- compatibilità con chiamate bet_type / side
- validate_selections coerente con micro-stake
- mixed dutching reale, non fallback cieco BACK
"""

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from typing import Dict, List, Tuple

# Set precisione globale per i calcoli monetari
getcontext().prec = 12

logger = logging.getLogger(__name__)

# Costanti operative
MIN_STAKE = Decimal("0.10")
STEP = Decimal("0.01")
MAX_WIN = Decimal("10000.00")


def _to_decimal(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def round_step(value: Decimal) -> Decimal:
    """Arrotonda al multiplo dello STEP configurato."""
    return (value / STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * STEP


def _normalize_price(value) -> Decimal:
    price = _to_decimal(value, "0")
    if price <= Decimal("1.01"):
        raise ValueError("Quota non valida (<= 1.01)")
    return price


def _normalize_side(selection: Dict, default_side: str) -> str:
    side = (
        selection.get("effectiveType")
        or selection.get("side")
        or default_side
        or "BACK"
    )
    side = str(side).upper().strip()
    if side not in ("BACK", "LAY"):
        side = "BACK"
    return side


def validate_selections(results: List[Dict], bet_type: str = "BACK") -> List[str]:
    """
    Valida selezioni per requisiti interni del motore matematico.
    Nota: il vincolo exchange dei 2€ è gestito dall'OMS micro-stake, non qui.
    """
    errors = []
    for r in results:
        runner = r.get("runnerName", str(r.get("selectionId", "?")))
        stake = _to_decimal(r.get("stake", 0), "0")

        if stake < MIN_STAKE:
            errors.append(f"{runner}: stake troppo basso ({stake:.2f} EUR)")

        price = _to_decimal(r.get("price", 0), "0")
        if price <= Decimal("1.01"):
            errors.append(f"{runner}: quota non valida ({price})")

        win = _to_decimal(
            r.get("profit_if_win", r.get("profitIfWins", 0)),
            "0",
        )
        if win > MAX_WIN:
            errors.append(f"{runner}: vincita massima superata ({win:.2f} > {MAX_WIN})")

    return errors


def calculate_dutching_stakes(
    selections: List[Dict],
    total_stake: float,
    bet_type: str = "BACK",
    commission: float = 4.5,
    side: str = None,
) -> Tuple[List[Dict], float, float]:
    """
    Entry point principale per calcolo dutching usando Decimal.

    Compatibile sia con:
    - calculate_dutching_stakes(..., bet_type="BACK")
    - calculate_dutching_stakes(..., side="BACK")
    - calculate_dutching_stakes(..., "BACK")
    """
    if not selections:
        return [], 0.0, 0.0

    mode = str(side or bet_type or "BACK").upper().strip()

    if mode == "BACK":
        return _calculate_back_dutching(selections, total_stake, commission)
    if mode == "LAY":
        return _calculate_lay_dutching(selections, total_stake, commission)

    raise ValueError(f"bet_type/side non supportato: {mode}")


def _calculate_back_dutching(
    selections: List[Dict], total_stake: float, commission: float
) -> Tuple[List[Dict], float, float]:
    total_stake_dec = _to_decimal(total_stake, "0")
    if total_stake_dec <= 0:
        return [], 0.0, 0.0

    comm_mult = Decimal("1") - (_to_decimal(commission, "0") / Decimal("100"))

    implied_probs = []
    for sel in selections:
        price = _normalize_price(sel.get("price", 0))
        implied_probs.append(Decimal("1") / price)

    book_value = sum(implied_probs)
    if book_value <= Decimal("0"):
        raise ValueError("Book value non valido")
    if book_value >= Decimal("1"):
        raise ValueError(f"Book value sfavorevole: {(book_value * 100):.2f}%")

    raw_stakes = []
    for i in range(len(selections)):
        stake = (total_stake_dec * implied_probs[i]) / book_value
        stake = round_step(stake)
        if stake < MIN_STAKE:
            stake = MIN_STAKE
        raw_stakes.append(stake)

    # riallineo il totale all'ammontare target spostando il delta sull'ultima selezione
    total_actual_stake = sum(raw_stakes)
    delta = round_step(total_stake_dec - total_actual_stake)

    if raw_stakes:
        adjusted_last = raw_stakes[-1] + delta
        if adjusted_last < MIN_STAKE:
            adjusted_last = MIN_STAKE
        raw_stakes[-1] = round_step(adjusted_last)

    total_actual_stake = sum(raw_stakes)

    results = []
    for i, sel in enumerate(selections):
        stake = raw_stakes[i]
        price = _normalize_price(sel["price"])
        gross_return = stake * price
        net_profit = (gross_return - total_actual_stake) * comm_mult

        results.append(
            {
                "selectionId": sel["selectionId"],
                "runnerName": sel.get("runnerName", str(sel["selectionId"])),
                "price": float(price),
                "stake": float(stake),
                "side": "BACK",
                "effectiveType": "BACK",
                "profitIfWins": float(round_step(net_profit)),
            }
        )

    avg_profit = sum(_to_decimal(r["profitIfWins"], "0") for r in results) / Decimal(
        str(len(results))
    )

    return results, float(round_step(avg_profit)), float(book_value * 100)


def _calculate_lay_dutching(
    selections: List[Dict], total_target_profit: float, commission: float
) -> Tuple[List[Dict], float, float]:
    """
    Modalità LAY:
    manteniamo la logica compatibile con il tuo file reale, ma permettiamo micro-stake.
    """
    target_profit_dec = _to_decimal(total_target_profit, "0")
    if target_profit_dec <= 0:
        return [], 0.0, 0.0

    implied_probs = []
    for sel in selections:
        price = _normalize_price(sel.get("price", 0))
        implied_probs.append(Decimal("1") / price)

    book_value = sum(implied_probs)
    if book_value <= Decimal("0"):
        raise ValueError("Book value non valido")

    results = []
    worst_liability = Decimal("0")

    stake = round_step(target_profit_dec)
    if stake < MIN_STAKE:
        stake = MIN_STAKE

    for sel in selections:
        price = _normalize_price(sel["price"])
        liability = stake * (price - Decimal("1"))
        if liability > worst_liability:
            worst_liability = liability

        results.append(
            {
                "selectionId": sel["selectionId"],
                "runnerName": sel.get("runnerName", str(sel["selectionId"])),
                "price": float(price),
                "stake": float(stake),
                "side": "LAY",
                "effectiveType": "LAY",
                "liability": float(round_step(liability)),
                "profitIfWins": float(round_step(target_profit_dec)),
            }
        )

    return results, float(round_step(target_profit_dec)), float(book_value * 100)


def dynamic_cashout_single(
    matched_stake: float,
    matched_price: float,
    current_price: float,
    commission: float = 4.5,
) -> dict:
    """Cashout usando Decimal."""
    ms = _to_decimal(matched_stake, "0")
    mp = _to_decimal(matched_price, "0")
    cp = _to_decimal(current_price, "0")

    if cp <= Decimal("1.01"):
        return {"lay_stake": 0.0, "green_up": 0.0}

    cashout_stake = (ms * mp) / cp
    cashout_stake = cashout_stake.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    profit_win = ms * (mp - Decimal("1")) - cashout_stake * (cp - Decimal("1"))
    profit_lose = cashout_stake - ms

    green = (profit_win + profit_lose) / Decimal("2")

    return {
        "lay_stake": float(cashout_stake),
        "green_up": float(green),
    }


def calculate_mixed_dutching(
    selections: List[Dict], amount: float, commission: float = 4.5
) -> Tuple[List[Dict], float, float]:
    """
    Mixed dutching reale:
    usa per ogni selezione il campo:
    - effectiveType
    oppure
    - side
    Se assenti, default BACK.
    """
    if not selections:
        return [], 0.0, 0.0

    total_amount_dec = _to_decimal(amount, "0")
    if total_amount_dec <= 0:
        return [], 0.0, 0.0

    weights = []
    normalized_sides = []

    for sel in selections:
        side = _normalize_side(sel, "BACK")
        price = _normalize_price(sel.get("price", 0))

        if side == "BACK":
            weight = Decimal("1") / price
        else:
            denom = price - Decimal("1")
            if denom <= 0:
                raise ValueError("Quota LAY non valida per mixed dutching")
            weight = Decimal("1") / denom

        weights.append(weight)
        normalized_sides.append(side)

    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("Peso totale non valido")

    raw_stakes = []
    for weight in weights:
        stake = (total_amount_dec * weight) / total_weight
        stake = round_step(stake)
        if stake < MIN_STAKE:
            stake = MIN_STAKE
        raw_stakes.append(stake)

    total_actual_stake = sum(raw_stakes)
    delta = round_step(total_amount_dec - total_actual_stake)

    if raw_stakes:
        adjusted_last = raw_stakes[-1] + delta
        if adjusted_last < MIN_STAKE:
            adjusted_last = MIN_STAKE
        raw_stakes[-1] = round_step(adjusted_last)

    total_actual_stake = sum(raw_stakes)

    results = []
    for i, sel in enumerate(selections):
        price = _normalize_price(sel["price"])
        side = normalized_sides[i]
        stake = raw_stakes[i]

        row = {
            "selectionId": sel["selectionId"],
            "runnerName": sel.get("runnerName", str(sel["selectionId"])),
            "price": float(price),
            "stake": float(stake),
            "side": side,
            "effectiveType": side,
        }

        if side == "LAY":
            row["liability"] = float(round_step(stake * (price - Decimal("1"))))

        results.append(row)

    # profitto stimato prudenziale semplice
    scenario_profits = []
    comm_mult = Decimal("1") - (_to_decimal(commission, "0") / Decimal("100"))

    for winner in results:
        winner_id = winner["selectionId"]
        pnl = Decimal("0")

        for r in results:
            price = _to_decimal(r["price"], "0")
            stake = _to_decimal(r["stake"], "0")
            side = r["effectiveType"]

            if side == "BACK":
                if r["selectionId"] == winner_id:
                    pnl += stake * (price - Decimal("1"))
                else:
                    pnl -= stake
            else:
                if r["selectionId"] == winner_id:
                    pnl -= stake * (price - Decimal("1"))
                else:
                    pnl += stake

        if pnl > 0:
            pnl *= comm_mult

        scenario_profits.append(pnl)

    min_profit = min(scenario_profits) if scenario_profits else Decimal("0")

    return results, float(round_step(min_profit)), float(total_weight * 100)