import logging
import time
from typing import Any, Callable

logger = logging.getLogger("CB")


class TransientError(Exception):
    """Errore temporaneo: ritentabile."""
    pass


class PermanentError(Exception):
    """Errore permanente: non ritentare."""
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int | None = None,
        max_failures: int | None = None,
        recovery_timeout: int | float | None = None,
        reset_timeout: int | float = 30,
    ):
        """
        Circuit breaker compatibile con naming legacy e attuale.

        Supporta:
        - failure_threshold (atteso dai test)
        - max_failures (usato dal codice attuale)
        - recovery_timeout
        - reset_timeout
        """
        if failure_threshold is not None:
            self.max_failures = int(failure_threshold)
        elif max_failures is not None:
            self.max_failures = int(max_failures)
        else:
            self.max_failures = 3

        if recovery_timeout is not None:
            self.reset_timeout = float(recovery_timeout)
        else:
            self.reset_timeout = float(reset_timeout)

        self.failures = 0
        self.opened_at = None

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.is_open():
            raise RuntimeError(
                "Circuit breaker OPEN - Chiamate API bloccate temporaneamente"
            )

        try:
            result = fn(*args, **kwargs)
            self._reset()
            return result

        except PermanentError:
            raise

        except TransientError as e:
            self._record_failure(e)
            raise

        except Exception as e:
            error_str = str(e).lower()

            # Errori permanenti
            if any(
                x in error_str
                for x in [
                    "insufficient_funds",
                    "market_closed",
                    "invalid_session",
                    "insufficient funds",
                    "market closed",
                    "invalid session",
                ]
            ):
                logger.error(
                    "[CB] Errore Permanente rilevato: %s. Operazione bloccata.",
                    e,
                )
                raise PermanentError(f"Errore Permanente: {e}") from e

            # Errori temporanei
            self._record_failure(e)
            raise TransientError(f"Errore Temporaneo: {e}") from e

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False

        if time.time() - self.opened_at > self.reset_timeout:
            self._reset()
            return False

        return True

    def _record_failure(self, error: Exception):
        self.failures += 1
        logger.warning(
            "[CB] Fallimento API (%s/%s): %s",
            self.failures,
            self.max_failures,
            error,
        )

        if self.failures >= self.max_failures:
            self.opened_at = time.time()
            logger.error(
                "[CB] CIRCUIT BREAKER APERTO per %.1f secondi!",
                self.reset_timeout,
            )

    def record_failure(self, error: Exception):
        self._record_failure(error)

    def _reset(self):
        if self.failures > 0 or self.opened_at is not None:
            logger.info("[CB] Circuit breaker RESET. Connessione ripristinata.")

        self.failures = 0
        self.opened_at = None

    def reset(self):
        self._reset()