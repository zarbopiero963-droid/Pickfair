import time
import logging
from typing import Callable, Any

logger = logging.getLogger("CB")

class TransientError(Exception): pass
class PermanentError(Exception): pass

class CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: int = 30):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.opened_at = None

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.is_open():
            raise RuntimeError("Circuit breaker OPEN - Chiamate API bloccate temporaneamente")

        try:
            result = fn(*args, **kwargs)
            self._reset()
            return result
        except Exception as e:
            error_str = str(e).lower()
            
            # Errori permanenti (Es. fondi insufficienti, mercato chiuso)
            if any(x in error_str for x in ['insufficient_funds', 'market_closed', 'invalid_session']):
                logger.error(f"[CB] Errore Permanente rilevato: {e}. Non scatta il breaker, ma blocco l'operazione.")
                raise PermanentError(f"Errore Permanente: {e}")
                
            # Errori temporanei (Es. Timeout, 502, network)
            self._record_failure(e)
            raise TransientError(f"Errore Temporaneo: {e}")

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.reset_timeout:
            self._reset()
            return False
        return True

    def _record_failure(self, error: Exception):
        self.failures += 1
        logger.warning(f"[CB] Fallimento API ({self.failures}/{self.max_failures}): {error}")
        if self.failures >= self.max_failures:
            self.opened_at = time.time()
            logger.error(f"[CB] CIRCUIT BREAKER APERTO per {self.reset_timeout} secondi!")

    def _reset(self):
        if self.failures > 0 or self.opened_at is not None:
            logger.info("[CB] Circuit breaker RESET. Connessione ripristinata.")
        self.failures = 0
        self.opened_at = None