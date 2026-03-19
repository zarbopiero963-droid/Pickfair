import logging
import time
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger("CB")


class State(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class PermanentError(Exception):
    pass


class TransientError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int | None = None,
        max_failures: int | None = None,
        recovery_time: float | None = None,
        recovery_timeout: float | None = None,
        reset_timeout: float = 30.0,
    ):
        # compat naming
        if failure_threshold is not None:
            self.max_failures = int(failure_threshold)
        elif max_failures is not None:
            self.max_failures = int(max_failures)
        else:
            self.max_failures = 3

        if recovery_time is not None:
            self.reset_timeout = float(recovery_time)
        elif recovery_timeout is not None:
            self.reset_timeout = float(recovery_timeout)
        else:
            self.reset_timeout = float(reset_timeout)

        self.state = State.CLOSED
        self.failures = 0
        self.opened_at = None

    # ---------------- CORE ---------------- #

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.is_open():
            raise RuntimeError(
                "Circuit breaker OPEN - Chiamate API bloccate temporaneamente"
            )

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result

        except PermanentError:
            raise

        except TransientError as e:
            self._on_failure(e)
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
                raise PermanentError(f"Errore Permanente: {e}") from e

            self._on_failure(e)
            raise TransientError(f"Errore Temporaneo: {e}") from e

    # ---------------- STATE ---------------- #

    def is_open(self) -> bool:
        if self.state != State.OPEN:
            return False

        if time.time() - self.opened_at > self.reset_timeout:
            self.state = State.HALF_OPEN
            return False

        return True

    def is_half_open(self) -> bool:
        return self.state == State.HALF_OPEN

    # ---------------- FAILURE ---------------- #

    def record_failure(self, error: Exception | None = None):
        self._on_failure(error)

    def _on_failure(self, error: Exception | None = None):
        self.failures += 1

        if error is None:
            error = RuntimeError("failure")

        logger.warning(
            "[CB] Failure (%s/%s): %s",
            self.failures,
            self.max_failures,
            error,
        )

        if self.failures >= self.max_failures:
            self.state = State.OPEN
            self.opened_at = time.time()
            logger.error(
                "[CB] OPEN for %.2fs",
                self.reset_timeout,
            )

    # ---------------- SUCCESS ---------------- #

    def _on_success(self):
        if self.state in (State.HALF_OPEN, State.OPEN):
            logger.info("[CB] Recovery -> CLOSED")

        self.reset()

    # ---------------- RESET ---------------- #

    def reset(self):
        self.state = State.CLOSED
        self.failures = 0
        self.opened_at = None