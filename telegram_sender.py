"""
Telegram Sender - Rate Limit Adattivo per invio messaggi.

Features:
    - Rate limit dinamico che si adatta a FloodWait
    - Aumenta delay dopo FloodWait
    - Diminuisce delay dopo successi consecutivi
    - Queue per messaggi in uscita
    - Metriche: messaggi inviati, FloodWait ricevuti, delay corrente
    - Thread-safe
"""

import time
import asyncio
import threading
import logging
from typing import Dict, Optional, Callable, Any
from queue import Queue, Empty
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Risultato invio messaggio."""
    success: bool
    message_id: Optional[int] = None
    chat_id: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 1
    flood_wait: int = 0


class AdaptiveRateLimiter:
    """
    Rate limiter adattivo per Telegram.
    
    Caratteristiche:
    - Delay base configurabile
    - Aumenta automaticamente dopo FloodWait
    - Diminuisce gradualmente dopo successi
    - Limiti min/max configurabili
    """
    
    def __init__(
        self,
        base_delay: float = 0.5,
        min_delay: float = 0.3,
        max_delay: float = 5.0,
        increase_factor: float = 1.5,
        decrease_factor: float = 0.9,
        decrease_after_successes: int = 10
    ):
        """
        Args:
            base_delay: Delay iniziale tra messaggi (secondi)
            min_delay: Delay minimo
            max_delay: Delay massimo
            increase_factor: Fattore moltiplicativo dopo errore
            decrease_factor: Fattore riduzione dopo successi
            decrease_after_successes: Successi consecutivi per ridurre delay
        """
        self.base_delay = base_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        self.decrease_after_successes = decrease_after_successes
        
        self._current_delay = base_delay
        self._consecutive_successes = 0
        self._last_flood_wait = 0
        self._last_send_time = 0.0
        self._lock = threading.RLock()
        
        self._total_flood_waits = 0
        self._total_sends = 0
        self._total_failures = 0
    
    def get_delay(self) -> float:
        """Delay corrente tra messaggi."""
        with self._lock:
            return self._current_delay
    
    def wait_if_needed(self):
        """Attende se necessario prima del prossimo invio."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_send_time
            if elapsed < self._current_delay:
                time.sleep(self._current_delay - elapsed)
    
    async def wait_if_needed_async(self):
        """Versione async di wait_if_needed."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_send_time
            if elapsed < self._current_delay:
                await asyncio.sleep(self._current_delay - elapsed)
    
    def record_success(self):
        """Registra invio riuscito."""
        with self._lock:
            self._last_send_time = time.time()
            self._total_sends += 1
            self._consecutive_successes += 1
            
            if self._consecutive_successes >= self.decrease_after_successes:
                if self._current_delay > self.min_delay:
                    old_delay = self._current_delay
                    self._current_delay = max(
                        self.min_delay,
                        self._current_delay * self.decrease_factor
                    )
                    logger.debug(f"[RATE_LIMIT] Delay reduced: {old_delay:.2f}s -> {self._current_delay:.2f}s")
                self._consecutive_successes = 0
    
    def record_flood_wait(self, wait_seconds: int):
        """Registra FloodWait ricevuto."""
        with self._lock:
            self._last_flood_wait = wait_seconds
            self._total_flood_waits += 1
            self._consecutive_successes = 0
            
            old_delay = self._current_delay
            self._current_delay = min(
                self.max_delay,
                max(self._current_delay * self.increase_factor, wait_seconds / 2)
            )
            logger.warning(f"[RATE_LIMIT] FloodWait {wait_seconds}s, delay increased: {old_delay:.2f}s -> {self._current_delay:.2f}s")
    
    def record_failure(self):
        """Registra errore generico."""
        with self._lock:
            self._total_failures += 1
            self._consecutive_successes = 0
            
            self._current_delay = min(
                self.max_delay,
                self._current_delay * 1.2
            )
    
    def reset(self):
        """Reset a valori iniziali."""
        with self._lock:
            self._current_delay = self.base_delay
            self._consecutive_successes = 0
            self._last_flood_wait = 0
    
    def get_stats(self) -> Dict:
        """Statistiche rate limiter."""
        with self._lock:
            return {
                'current_delay': round(self._current_delay, 2),
                'base_delay': self.base_delay,
                'min_delay': self.min_delay,
                'max_delay': self.max_delay,
                'consecutive_successes': self._consecutive_successes,
                'last_flood_wait': self._last_flood_wait,
                'total_sends': self._total_sends,
                'total_flood_waits': self._total_flood_waits,
                'total_failures': self._total_failures,
                'success_rate': round(
                    self._total_sends / max(1, self._total_sends + self._total_failures) * 100, 1
                )
            }


@dataclass
class QueuedMessage:
    """Messaggio in coda per invio."""
    chat_id: str
    text: str
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    max_retries: int = 3
    retry_count: int = 0
    callback: Optional[Callable] = None


class TelegramSender:
    """
    Sender Telegram con rate limit adattivo e queue.
    
    Features:
    - Queue messaggi con priorita
    - Rate limit adattivo
    - Retry automatici
    - Callback su completamento
    - Metriche dettagliate
    """
    
    def __init__(
        self,
        client,
        base_delay: float = 0.5,
        max_queue_size: int = 100
    ):
        """
        Args:
            client: Telethon client
            base_delay: Delay base tra messaggi
            max_queue_size: Dimensione massima coda
        """
        self.client = client
        self.rate_limiter = AdaptiveRateLimiter(base_delay=base_delay)
        self._queue: Queue = Queue(maxsize=max_queue_size)
        self._running = False
        self._worker_thread = None
        self._lock = threading.RLock()
        
        self._messages_sent = 0
        self._messages_failed = 0
        self._messages_queued = 0
    
    def queue_message(
        self,
        chat_id: str,
        text: str,
        priority: int = 0,
        callback: Callable = None
    ) -> bool:
        """
        Aggiunge messaggio alla coda.
        
        Args:
            chat_id: ID chat destinazione
            text: Testo messaggio
            priority: Priorita (0 = normale, 1+ = alta)
            callback: Funzione chiamata al completamento
        
        Returns:
            True se aggiunto, False se coda piena
        """
        try:
            msg = QueuedMessage(
                chat_id=chat_id,
                text=text,
                priority=priority,
                callback=callback
            )
            self._queue.put_nowait(msg)
            self._messages_queued += 1
            return True
        except Exception as e:
            logger.warning(f"[TG_SENDER] Queue full, message dropped: {e}")
            return False
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        max_retries: int = 3
    ) -> SendResult:
        """
        Invia messaggio con rate limit e retry.
        
        Returns:
            SendResult con esito
        """
        result = SendResult(success=False, chat_id=chat_id)
        
        for attempt in range(max_retries):
            result.attempts = attempt + 1
            
            await self.rate_limiter.wait_if_needed_async()
            
            try:
                entity = await self.client.get_entity(int(chat_id))
                msg = await self.client.send_message(entity, text)
                
                result.success = True
                result.message_id = msg.id if hasattr(msg, 'id') else None
                
                self.rate_limiter.record_success()
                self._messages_sent += 1
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                if 'floodwait' in error_str or 'flood' in error_str:
                    try:
                        wait_seconds = int(''.join(filter(str.isdigit, str(e)))) or 60
                    except:
                        wait_seconds = 60
                    
                    result.flood_wait = wait_seconds
                    self.rate_limiter.record_flood_wait(wait_seconds)
                    
                    await asyncio.sleep(wait_seconds + 1)
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
        max_retries: int = 3
    ) -> SendResult:
        """Versione sincrona di send_message."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.send_message(chat_id, text, max_retries)
            )
        finally:
            loop.close()
    
    def start_worker(self):
        """Avvia worker thread per processare coda."""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("[TG_SENDER] Worker started")
    
    def stop_worker(self):
        """Ferma worker thread."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("[TG_SENDER] Worker stopped")
    
    def _worker_loop(self):
        """Loop worker per processare messaggi in coda."""
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
                        logger.error(f"[TG_SENDER] Callback error: {e}")
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"[TG_SENDER] Worker error: {e}")
        
        loop.close()
    
    def get_queue_size(self) -> int:
        """Dimensione attuale coda."""
        return self._queue.qsize()
    
    def get_stats(self) -> Dict:
        """Statistiche sender."""
        return {
            'rate_limiter': self.rate_limiter.get_stats(),
            'queue_size': self.get_queue_size(),
            'messages_sent': self._messages_sent,
            'messages_failed': self._messages_failed,
            'messages_queued': self._messages_queued,
            'worker_running': self._running
        }
    
    def reset_stats(self):
        """Reset statistiche."""
        self._messages_sent = 0
        self._messages_failed = 0
        self._messages_queued = 0
        self.rate_limiter.reset()


_global_sender = None


def get_telegram_sender(client=None, base_delay: float = 0.5) -> Optional[TelegramSender]:
    """Singleton sender globale."""
    global _global_sender
    if _global_sender is None and client is not None:
        _global_sender = TelegramSender(client, base_delay=base_delay)
    return _global_sender


def init_telegram_sender(client, base_delay: float = 0.5) -> TelegramSender:
    """Inizializza sender globale."""
    global _global_sender
    _global_sender = TelegramSender(client, base_delay=base_delay)
    return _global_sender
