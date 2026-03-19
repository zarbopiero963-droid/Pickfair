"""
PnL Engine - Calcolo P&L live per selezione

Questo modulo calcola il profitto/perdita in tempo reale per ogni selezione,
utilizzando le quote live e formule coerenti di green-up/cashout.
"""

import logging
from typing import Dict, Optional, List

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

    # =========================================================
    # BACK / LAY LIVE PnL
    # =========================================================

    def calculate_back_pnl(self, order: Dict, best_lay_price: float) -> float:
        if order.get("side") != "BACK":
            return 0.0

        stake = float(order.get("sizeMatched", order.get("stake", 0)) or 0)
        price = float(order.get("averagePriceMatched", order.get("price", 0)) or 0)

        if stake <= 0 or price <= 1 or best_lay_price <= 1:
            return 0.0

        try:
            result = dynamic_cashout_single(
                back_stake=stake,
                back_price=price,
                lay_price=best_lay_price,
                commission=self.commission,
            )
            return round(float(result.get("net_profit", 0) or 0), 2)
        except Exception as e:
            logger.error(f"Errore calcolo P&L BACK: {e}")
            return 0.0

    def calculate_lay_pnl(self, order: Dict, best_back_price: float) -> float:
        if order.get("side") != "LAY":
            return 0.0

        stake = float(order.get("sizeMatched", order.get("stake", 0)) or 0)
        price = float(order.get("averagePriceMatched", order.get("price", 0)) or 0)

        if stake <= 0 or price <= 1 or best_back_price <= 1:
            return 0.0

        try:
            back_stake = (stake * price) / float(best_back_price)

            pnl_if_win = stake - (back_stake * float(best_back_price))
            pnl_if_lose = stake - back_stake

            green = min(pnl_if_win, pnl_if_lose)

            if green > 0:
                green *= 1 - (self.commission / 100.0)

            return round(green, 2)
        except Exception as e:
            logger.error(f"Errore calcolo P&L LAY: {e}")
            return 0.0

    def calculate_order_pnl(
        self, order: Dict, best_back: float, best_lay: float
    ) -> float:
        side = order.get("side", "")

        if side == "BACK":
            return self.calculate_back_pnl(order, best_lay)
        elif side == "LAY":
            return self.calculate_lay_pnl(order, best_back)

        return 0.0

    def calculate_selection_pnl(
        self, orders: List[Dict], best_back: float, best_lay: float
    ) -> float:
        total_pnl = 0.0
        for order in orders:
            total_pnl += self.calculate_order_pnl(order, best_back, best_lay)
        return round(total_pnl, 2)

    # =========================================================
    # AUTO GREEN
    # =========================================================

    @staticmethod
    def is_auto_green_eligible(
        order: Dict, current_time: Optional[float] = None
    ) -> bool:
        import time
        from trading_config import AUTO_GREEN_DELAY_SEC

        if not order.get("auto_green", False):
            return False

        if order.get("simulation", False):
            return False

        placed_at = order.get("placed_at", 0)
        if not placed_at:
            return False

        now = current_time or time.time()
        elapsed = now - placed_at

        if elapsed < AUTO_GREEN_DELAY_SEC:
            logger.debug(
                f"Auto-green: {elapsed:.1f}s < {AUTO_GREEN_DELAY_SEC}s grace period"
            )
            return False

        return True

    # =========================================================
    # PREVIEW SINGLE
    # =========================================================

    def calculate_preview(self, selection: Dict, side: str = "BACK") -> Dict:
        stake = float(selection.get("stake", selection.get("presetStake", 5.0)) or 0)
        price = float(selection.get("price", 2.0) or 0)
        commission_pct = self.commission / 100.0
        side = str(side or "BACK").upper().strip()

        if stake <= 0 or price <= 1:
            return {
                "profit_if_win": 0.0,
                "profit_if_lose": 0.0,
                "net_profit": 0.0,
                "liability": 0.0,
            }

        if side == "BACK":
            gross_profit = stake * (price - 1)
            profit_if_win = gross_profit * (1 - commission_pct)
            profit_if_lose = -stake
            liability = 0.0
            net_profit = profit_if_win

        else:  # LAY
            liability = stake * (price - 1)
            profit_if_win = -liability
            profit_if_lose = stake * (1 - commission_pct)
            net_profit = profit_if_lose

        return {
            "profit_if_win": round(profit_if_win, 2),
            "profit_if_lose": round(profit_if_lose, 2),
            "net_profit": round(net_profit, 2),
            "liability": round(liability, 2),
        }

    # =========================================================
    # PREVIEW MULTI-RUNNER (DUTCHING)
    # =========================================================

    def calculate_multi_runner_preview(
        self,
        selections: List[Dict],
        mode: str = "BACK",
    ) -> Dict:
        mode = str(mode or "BACK").upper().strip()
        commission_pct = self.commission / 100.0

        if not selections:
            return {
                "scenarios": [],
                "min_profit": 0.0,
                "max_profit": 0.0,
                "avg_profit": 0.0,
                "total_stake": 0.0,
                "total_liability": 0.0,
                "implied_probability": 0.0,
            }

        normalized = []
        total_stake = 0.0
        total_liability = 0.0
        implied_probability = 0.0

        for sel in selections:
            stake = float(sel.get("stake", sel.get("presetStake", 0.0)) or 0.0)
            price = float(sel.get("price", 0.0) or 0.0)
            selection_id = sel.get("selectionId")
            runner_name = str(sel.get("runnerName", selection_id or "Runner"))

            if stake <= 0 or price <= 1:
                continue

            side = str(
                sel.get("side") or sel.get("effectiveType") or mode
            ).upper().strip()

            if side not in ("BACK", "LAY"):
                side = "BACK"

            liability = stake * (price - 1) if side == "LAY" else 0.0

            normalized.append(
                {
                    "selectionId": selection_id,
                    "runnerName": runner_name,
                    "side": side,
                    "stake": stake,
                    "price": price,
                    "liability": liability,
                }
            )

            total_stake += stake
            total_liability += liability
            implied_probability += 1.0 / price

        scenarios = []

        for winner in normalized:
            winner_id = winner["selectionId"]
            pnl = 0.0

            for sel in normalized:
                stake = sel["stake"]
                price = sel["price"]
                side = sel["side"]
                selection_id = sel["selectionId"]

                if side == "BACK":
                    if selection_id == winner_id:
                        pnl += stake * (price - 1.0)
                    else:
                        pnl -= stake
                else:
                    if selection_id == winner_id:
                        pnl -= stake * (price - 1.0)
                    else:
                        pnl += stake

            if pnl > 0:
                pnl *= (1.0 - commission_pct)

            scenarios.append(
                {
                    "winner_selection_id": winner_id,
                    "winner_runner_name": winner["runnerName"],
                    "profit": round(pnl, 2),
                }
            )

        profits = [row["profit"] for row in scenarios]

        return {
            "scenarios": scenarios,
            "min_profit": round(min(profits), 2) if profits else 0.0,
            "max_profit": round(max(profits), 2) if profits else 0.0,
            "avg_profit": round(sum(profits) / len(profits), 2) if profits else 0.0,
            "total_stake": round(total_stake, 2),
            "total_liability": round(total_liability, 2),
            "implied_probability": round(implied_probability * 100.0, 2),
        }