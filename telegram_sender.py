"""
Telegram Sender - Gestisce l'invio asincrono di messaggi Telegram.
HEDGE-FUND STABLE:
- Anti-FloodWait Loop
- Adaptive Rate Limiting
- No-blocking Queue
- EventBus integration per MASTER copy-trading
"""

import asyncio
import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Dict, Optional

logger = logging.getLogger("TG_SENDER")


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
    def __init__(self, client, base_delay: float = 0.5, event_bus=None, default_chat_id: Optional[str] = None):
        self.client = client
        self.bus = event_bus
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

    # =========================================================
    # LOW-LEVEL SEND
    # =========================================================

    async def send_message(
        self,
        chat_id: str,
        text: str,
        max_retries: int = 3,
    ) -> SendResult:
        result = SendResult()

        for attempt in range(max_retries):
            await self.rate_limiter.wait_if_needed_async()

            try:
                entity = await self.client.get_entity(int(chat_id))
                msg = await self.client.send_message(entity, text)

                result.success = True
                result.message_id = msg.id if hasattr(msg, "id") else None

                self.rate_limiter.record_success()
                self._messages_sent += 1
                return result

            except Exception as e:
                error_str = str(e).lower()

                if "floodwait" in error_str or "flood" in error_str:
                    try:
                        wait_seconds = int("".join(filter(str.isdigit, str(e)))) or 60
                    except Exception:
                        wait_seconds = 60

                    result.flood_wait = wait_seconds
                    self.rate_limiter.record_flood_wait(wait_seconds)

                    if attempt >= max_retries - 1:
                        result.error = f"FloodWait ({wait_seconds}s) max retries reached."
                        break

                    safe_wait = min(wait_seconds, 15)
                    logger.warning(
                        "[TG_SENDER] FloodWait %ss. Safe sleep: %ss. Attempt %s/%s",
                        wait_seconds,
                        safe_wait,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(safe_wait)
                    continue

                result.error = str(e)
                self.rate_limiter.record_failure()

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        self._messages_failed += 1
        return result

    def send_message_sync(
        self,
        chat_id: str,
        text: str,
        max_retries: int = 3,
    ) -> SendResult:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.send_message(chat_id, text, max_retries)
            )
        finally:
            loop.close()

    def queue_message(
        self,
        chat_id: str,
        text: str,
        max_retries: int = 3,
        callback: Optional[Callable] = None,
    ):
        msg = QueuedMessage(
            chat_id=str(chat_id),
            text=text,
            max_retries=max_retries,
            callback=callback,
        )
        self._queue.put(msg)
        self._messages_queued += 1

        if not self._running:
            self.start_worker()

    def queue_default_message(
        self,
        text: str,
        max_retries: int = 3,
        callback: Optional[Callable] = None,
    ):
        if not self.default_chat_id:
            logger.warning("[TG_SENDER] Nessun default_chat_id configurato.")
            return
        self.queue_message(
            chat_id=self.default_chat_id,
            text=text,
            max_retries=max_retries,
            callback=callback,
        )

    def start_worker(self):
        if self._running:
            return

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="TelegramSenderWorker",
        )
        self._worker_thread.start()
        logger.info("[TG_SENDER] Worker started")

    def stop_worker(self):
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("[TG_SENDER] Worker stopped")

    def _worker_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            try:
                msg = self._queue.get(timeout=1)

                result = loop.run_until_complete(
                    self.send_message(msg.chat_id, msg.text, msg.max_retries)
                )

                if msg.callback:
                    try:
                        msg.callback(result)
                    except Exception as e:
                        logger.error("[TG_SENDER] Callback error: %s", e)

                self._queue.task_done()

            except Empty:
                continue
            except Exception as e:
                logger.error("[TG_SENDER] Worker error: %s", e)

        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()

    # =========================================================
    # MASTER SIGNAL FORMATTERS
    # =========================================================

    def _escape(self, value):
        if value is None:
            return ""
        return str(value)

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
        return (
            "🟢 MASTER SIGNAL\n\n"
            f"event_name: {self._escape(event_name)}\n"
            f"market_name: {self._escape(market_name)}\n"
            f"selection: {self._escape(runner_name)}\n"
            f"action: {self._escape(action)}\n"
            f"master_price: {float(price):.2f}\n"
            f"market_id: {self._escape(market_id)}\n"
            f"selection_id: {self._escape(selection_id)}\n"
            f"status: {self._escape(status)}"
        )

    def _format_dutching_signal(self, data: Dict) -> str:
        event_name = self._escape(data.get("event_name", ""))
        market_name = self._escape(data.get("market_name", ""))
        market_id = self._escape(data.get("market_id", ""))
        status = self._escape(data.get("status", "MATCHED"))
        selections = data.get("selections", []) or []

        lines = [
            "🔵 MASTER SIGNAL DUTCHING",
            "",
            f"event_name: {event_name}",
            f"market_name: {market_name}",
            f"market_id: {market_id}",
            f"status: {status}",
            "",
            "legs:",
        ]

        for idx, sel in enumerate(selections, start=1):
            runner_name = self._escape(sel.get("runnerName", sel.get("selectionId", "")))
            action = self._escape(
                str(
                    sel.get("effectiveType")
                    or sel.get("side")
                    or data.get("bet_type", "BACK")
                ).upper()
            )
            price = float(sel.get("price", 0.0) or 0.0)
            selection_id = self._escape(sel.get("selectionId", ""))

            lines.append(
                f"{idx}) {runner_name} | {action} | {price:.2f} | selection_id={selection_id}"
            )

        return "\n".join(lines)

    # =========================================================
    # EVENT BUS HANDLERS
    # =========================================================

    def _on_quick_bet_success(self, data: Dict):
        if data.get("sim", False):
            return
        if not self.default_chat_id:
            return

        runner = data.get("runner_name", "Ignoto")
        price = float(data.get("price", 0.0) or 0.0)
        action = str(data.get("bet_type", "BACK")).upper()
        market_id = data.get("market_id", "")
        selection_id = data.get("selection_id", "")
        event_name = data.get("event_name", "")
        market_name = data.get("market_name", "")
        status = data.get("status", "MATCHED")

        text = self._format_single_signal(
            runner_name=runner,
            action=action,
            price=price,
            market_id=market_id,
            selection_id=selection_id,
            event_name=event_name,
            market_name=market_name,
            status=status,
        )
        self.queue_default_message(text)

    def _on_dutching_success(self, data: Dict):
        if data.get("sim", False):
            return
        if not self.default_chat_id:
            return

        text = self._format_dutching_signal(data)
        self.queue_default_message(text)

    def _on_cashout_success(self, data: Dict):
        if not self.default_chat_id:
            return

        green = float(data.get("green_up", 0.0) or 0.0)
        status = self._escape(data.get("status", "DONE"))

        text = (
            "🚨 CASHOUT ESEGUITO\n\n"
            f"green_up: {green:.2f}\n"
            f"status: {status}"
        )
        self.queue_default_message(text)

    # =========================================================
    # STATS
    # =========================================================

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> Dict:
        return {
            "rate_limiter": self.rate_limiter.get_stats(),
            "queue_size": self.get_queue_size(),
            "messages_sent": self._messages_sent,
            "messages_failed": self._messages_failed,
            "messages_queued": self._messages_queued,
            "worker_running": self._running,
        }

    def reset_stats(self):
        self._messages_sent = 0
        self._messages_failed = 0
        self._messages_queued = 0
        self.rate_limiter.reset()


_global_sender = None


def get_telegram_sender(
    client=None,
    base_delay: float = 0.5,
    event_bus=None,
    default_chat_id: Optional[str] = None,
) -> Optional[TelegramSender]:
    global _global_sender
    if _global_sender is None and client is not None:
        _global_sender = TelegramSender(
            client=client,
            base_delay=base_delay,
            event_bus=event_bus,
            default_chat_id=default_chat_id,
        )
    return _global_sender


def init_telegram_sender(
    client,
    base_delay: float = 0.5,
    event_bus=None,
    default_chat_id: Optional[str] = None,
) -> TelegramSender:
    global _global_sender
    _global_sender = TelegramSender(
        client=client,
        base_delay=base_delay,
        event_bus=event_bus,
        default_chat_id=default_chat_id,
    )
    return _global_sender