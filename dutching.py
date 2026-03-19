"""
Dutching Engine per Betfair Exchange.
Calcolo stake ottimali per profitto uniforme su multiple selezioni.
Compatibile con chiamate legacy/tests:
- calculate_dutching_stakes
- calculate_mixed_dutching
- calculate_ai_mixed_stakes
- calculate_ai_mixed_dutching
- dynamic_cashout_single
- validate_selections
"""

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from typing import Dict, List, Tuple

getcontext().prec = 12

logger = logging.getLogger(__name__)

MIN_STAKE = Decimal("0.10")
STEP = Decimal("0.01")
MAX_WIN = Decimal("10000.00")


def _to_decimal(value, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def round_step(value: Decimal) -> Decimal:
    return (value / STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * STEP


def format_currency(value) -> str:
    amount = _to_decimal(value, "0")
    return f"€{amount:.2f}"


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
    errors: List[str] = []

    for r in results:
        runner = str(r.get("runnerName", str(r.get("selectionId", "?"))))
        stake = _to_decimal(r.get("stake", 0), "0")

        if stake < MIN_STAKE:
            errors.append(f"{runner}: stake troppo basso ({stake:.2f} EUR)")

        price = _to_decimal(r.get("price", 0), "0")
        if price <= Decimal("1.01"):
            errors.append(f"{runner}: quota non valida ({price})")

        win = _to_decimal(r.get("profit_if_win", r.get("profitIfWins", 0)), "0")
        if win > MAX_WIN:
            errors.append(f"{runner}: vincita massima superata ({win:.2f} > {MAX_WIN})")

    return errors


def calculate_dutching_stakes(
    selections: List[Dict],
    total_stake: float,
    bet_type: str = "BACK",
    commission: float = 4.5,
    side: str = None,
    **kwargs,
) -> Tuple[List[Dict], float, float]:
    if not selections:
        return [], 0.0, 0.0

    mode = str(side or bet_type or "BACK").upper().strip()

    if mode == "BACK":
        return _calculate_back_dutching(selections, total_stake, commission)
    if mode == "LAY":
        return _calculate_lay_dutching(selections, total_stake, commission)

    raise ValueError(f"bet_type/side non supportato: {mode}")


# ✅ FIX COMPATIBILITÀ LEGACY
def calculate_dutching(
    selections,
    total_stake: float,
    bet_type: str = "BACK",
    commission: float = 4.5,
    side: str = None,
    **kwargs,
):
    legacy_mode = selections and not isinstance(selections[0], dict)
    if legacy_mode:
        selections = [
            {"selectionId": i, "runnerName": str(i), "price": float(p)}
            for i, p in enumerate(selections)
        ]
    results, profit, implied_prob = calculate_dutching_stakes(
        selections=selections,
        total_stake=total_stake,
        bet_type=bet_type,
        commission=commission,
        side=side,
        **kwargs,
    )
    if legacy_mode:
        return {
            "stakes": [r["stake"] for r in results],
            "profits": [r["profitIfWins"] for r in results],
            "results": results,
            "profit": profit,
            "implied_probability": implied_prob,
        }
    return results, profit, implied_prob


def _calculate_back_dutching(
    selections: List[Dict],
    total_stake: float,
    commission: float,
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

    raw_stakes = []
    for prob in implied_probs:
        stake = (total_stake_dec * prob) / book_value
        stake = round_step(stake)
        if stake < MIN_STAKE:
            stake = MIN_STAKE
        raw_stakes.append(stake)

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
                "runnerName": str(sel.get("runnerName", str(sel["selectionId"]))),
                "price": float(price),
                "stake": float(stake),
                "side": "BACK",
                "effectiveType": "BACK",
                "profitIfWins": float(round_step(net_profit)),
            }
        )

    avg_profit = sum(
        _to_decimal(r["profitIfWins"], "0") for r in results
    ) / Decimal(str(len(results) or 1))

    return results, float(round_step(avg_profit)), float(book_value * 100)


def _calculate_lay_dutching(
    selections: List[Dict],
    total_target_profit: float,
    commission: float,
) -> Tuple[List[Dict], float, float]:
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
    stake = round_step(target_profit_dec)
    if stake < MIN_STAKE:
        stake = MIN_STAKE

    for sel in selections:
        price = _normalize_price(sel["price"])
        liability = stake * (price - Decimal("1"))

        results.append(
            {
                "selectionId": sel["selectionId"],
                "runnerName": str(sel.get("runnerName", str(sel["selectionId"]))),
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
    matched_stake: float = None,
    matched_price: float = None,
    current_price: float = None,
    commission: float = 4.5,
    **kwargs,
) -> dict:
    if matched_stake is None:
        matched_stake = kwargs.get("back_stake", 0.0)
    if matched_price is None:
        matched_price = kwargs.get("back_price", 0.0)
    if current_price is None:
        current_price = kwargs.get("lay_price", 0.0)

    ms = _to_decimal(matched_stake, "0")
    mp = _to_decimal(matched_price, "0")
    cp = _to_decimal(current_price, "0")

    if ms <= Decimal("0") or mp <= Decimal("1.01") or cp <= Decimal("1.01"):
        return {
            "lay_stake": 0.0,
            "green_up": 0.0,
            "net_profit": 0.0,
        }

    cashout_stake = (ms * mp) / cp
    cashout_stake = cashout_stake.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    profit_win = ms * (mp - Decimal("1")) - cashout_stake * (cp - Decimal("1"))
    profit_lose = cashout_stake - ms
    green = (profit_win + profit_lose) / Decimal("2")
    green = green.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "lay_stake": float(cashout_stake),
        "green_up": float(green),
        "net_profit": float(green),
    }


def calculate_mixed_dutching(
    selections: List[Dict],
    amount: float,
    commission: float = 4.5,
    **kwargs,
) -> Tuple[List[Dict], float, float]:
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
    if total_weight <= Decimal("0"):
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

    results = []
    for i, sel in enumerate(selections):
        price = _normalize_price(sel["price"])
        side = normalized_sides[i]
        stake = raw_stakes[i]

        row = {
            "selectionId": sel["selectionId"],
            "runnerName": str(sel.get("runnerName", str(sel["selectionId"]))),
            "price": float(price),
            "stake": float(stake),
            "side": side,
            "effectiveType": side,
        }

        if side == "LAY":
            row["liability"] = float(round_step(stake * (price - Decimal("1"))))

        results.append(row)

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


def calculate_ai_mixed_stakes(
    selections: List[Dict],
    amount: float = None,
    commission: float = 4.5,
    total_stake: float = None,
    **kwargs,
) -> Tuple[List[Dict], float, float]:
    if amount is None:
        amount = total_stake
    if amount is None:
        amount = kwargs.get("stake", 0.0)
    return calculate_mixed_dutching(selections, amount, commission)


def calculate_ai_mixed_dutching(
    selections: List[Dict],
    amount: float,
    commission: float = 4.5,
    **kwargs,
) -> Tuple[List[Dict], float, float]:
    return calculate_mixed_dutching(selections, amount, commission)
