"""
Telegram Sender - Gestisce l'invio asincrono di messaggi Telegram.
HEDGE-FUND STABLE:
- Anti-FloodWait Loop
- Adaptive Rate Limiting
- No-blocking Queue
- EventBus integration per MASTER copy-trading
- Database logging outbox
"""

import asyncio
import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Dict, Optional

logger = logging.getLogger("TG_SENDER")


# ===============================
# ✅ NUOVA FUNZIONE (PER TEST)
# ===============================

def format_bet_message(
    runner_name: str,
    action: str,
    price: float,
    market_id: str = "",
    selection_id: str = "",
    event_name: str = "",
    market_name: str = "",
    status: str = "MATCHED",
) -> str:
    safe_runner = "" if runner_name is None else str(runner_name)
    safe_action = "" if action is None else str(action).upper().strip()
    safe_market_id = "" if market_id is None else str(market_id)
    safe_selection_id = "" if selection_id is None else str(selection_id)
    safe_event_name = "" if event_name is None else str(event_name)
    safe_market_name = "" if market_name is None else str(market_name)
    safe_status = "" if status is None else str(status)

    try:
        safe_price = float(price)
    except Exception:
        safe_price = 0.0

    return (
        "🟢 MASTER SIGNAL\n\n"
        f"event_name: {safe_event_name}\n"
        f"market_name: {safe_market_name}\n"
        f"selection: {safe_runner}\n"
        f"action: {safe_action}\n"
        f"master_price: {safe_price:.2f}\n"
        f"market_id: {safe_market_id}\n"
        f"selection_id: {safe_selection_id}\n"
        f"status: {safe_status}"
    )


@dataclass
class SendResult:
    success: bool = False
    message_id: Optional[int] = None
    error: Optional[str] = None
    flood_wait: Optional[int] = None


@dataclass
class QueuedMessage:
    chat_id: str
    text: str
    max_retries: int = 3
    callback: Optional[Callable] = None
    message_type: str = "GENERIC"


class AdaptiveRateLimiter:
    def __init__(self, base_delay: float = 0.5):
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.last_send_time = 0.0
        self._lock = threading.Lock()
        self.consecutive_successes = 0

    async def wait_if_needed_async(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_send_time
        if elapsed < self.current_delay:
            await asyncio.sleep(self.current_delay - elapsed)
        self.last_send_time = asyncio.get_event_loop().time()

    def record_success(self):
        with self._lock:
            self.consecutive_successes += 1
            if self.consecutive_successes > 10:
                self.current_delay = max(self.base_delay, self.current_delay * 0.9)
                self.consecutive_successes = 0

    def record_failure(self):
        with self._lock:
            self.consecutive_successes = 0
            self.current_delay = min(self.base_delay * 5, self.current_delay * 1.5)

    def record_flood_wait(self, wait_seconds: int):
        with self._lock:
            self.consecutive_successes = 0
            self.current_delay = max(
                self.current_delay,
                min(wait_seconds / 10.0, self.base_delay * 10),
            )

    def get_stats(self):
        return {
            "current_delay": self.current_delay,
            "consecutive_successes": self.consecutive_successes,
        }

    def reset(self):
        self.current_delay = self.base_delay
        self.consecutive_successes = 0


class TelegramSender:
    def __init__(
        self,
        client,
        base_delay: float = 0.5,
        event_bus=None,
        default_chat_id: Optional[str] = None,
        db=None,
    ):
        self.client = client
        self.bus = event_bus
        self.db = db
        self.default_chat_id = str(default_chat_id) if default_chat_id not in (None, "") else None

        self.rate_limiter = AdaptiveRateLimiter(base_delay)
        self._queue = Queue()
        self._running = False
        self._worker_thread = None

        self._messages_sent = 0
        self._messages_failed = 0
        self._messages_queued = 0

        if self.bus is not None:
            self.bus.subscribe("QUICK_BET_SUCCESS", self._on_quick_bet_success)
            self.bus.subscribe("DUTCHING_SUCCESS", self._on_dutching_success)
            self.bus.subscribe("CASHOUT_SUCCESS", self._on_cashout_success)

    def _escape(self, value):
        if value is None:
            return ""
        return str(value)

    # ===============================
    # ✅ MODIFICATO QUI
    # ===============================

    def _format_single_signal(
        self,
        runner_name,
        action,
        price,
        market_id,
        selection_id,
        event_name="",
        market_name="",
        status="MATCHED",
    ) -> str:
        return format_bet_message(
            runner_name=runner_name,
            action=action,
            price=price,
            market_id=market_id,
            selection_id=selection_id,
            event_name=event_name,
            market_name=market_name,
            status=status,
        )