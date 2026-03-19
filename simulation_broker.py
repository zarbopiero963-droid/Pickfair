import logging
import time
from typing import Any, Callable


logger = logging.getLogger("CB")


class PermanentError(Exception):
    """Errore permanente: non ritentare."""
    pass


class TransientError(Exception):
    """Errore temporaneo: ritentabile."""
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int | None = None,
        max_failures: int | None = None,
        recovery_timeout: float | None = None,
        reset_timeout: float | None = None,
    ):
        """
        Circuit Breaker compatibile con naming legacy e nuovo.

        Supporta:
        - failure_threshold (atteso da alcuni test)
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
        elif reset_timeout is not None:
            self.reset_timeout = float(reset_timeout)
        else:
            self.reset_timeout = 30.0

        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"

    def is_open(self) -> bool:
        if self.state != "OPEN":
            return False

        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.reset_timeout:
            self.state = "CLOSED"
            self.failure_count = 0
            return False

        return True

    def _reset(self) -> None:
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"

    def reset(self) -> None:
        self._reset()

    def _record_failure(self, error: Exception) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()

        logger.warning(
            "[CB] Fallimento API (%s/%s): %s",
            self.failure_count,
            self.max_failures,
            error,
        )

        if self.failure_count >= self.max_failures:
            self.state = "OPEN"
            logger.error(
                "[CB] Circuit breaker OPEN per %.1fs",
                self.reset_timeout,
            )

    def record_failure(self, error: Exception) -> None:
        self._record_failure(error)

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
                logger.error("[CB] Errore Permanente rilevato: %s", e)
                raise PermanentError(f"Errore Permanente: {e}") from e

            self._record_failure(e)
            raise TransientError(f"Errore Temporaneo: {e}") from e