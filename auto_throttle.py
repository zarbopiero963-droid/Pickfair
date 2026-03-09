"""
Auto Throttle - DEPRECATED / LEGACY COMPAT

Questo modulo è stato ufficialmente dismesso.

Nella nuova architettura OMS:
- la protezione anti-spam (doppi click) è gestita in core/risk_middleware.py
- il rate-limiting applicativo è gestito da timer UI / executor / scheduler
- il blocco chiamate in caso di errore è gestito da circuit breaker e OMS

Manteniamo questo file solo per retrocompatibilità con codice legacy
che potrebbe ancora importarlo o chiamarne alcuni metodi.
"""

import logging

logger = logging.getLogger("AutoThrottle")


class AutoThrottle:
    def __init__(self, *args, **kwargs):
        logger.warning(
            "[DEPRECATED] AutoThrottle istanziato. "
            "Usare RiskMiddleware / Executor / OMS."
        )
        self._last_rate = 0.0
        self._blocked = False

    def wait(self):
        """Metodo legacy: non blocca più nulla."""
        return None

    def record_call(self):
        """Metodo legacy: no-op."""
        return None

    def get_current_rate(self):
        """Metodo legacy."""
        return self._last_rate

    def update(self, *args, **kwargs):
        """
        Metodo legacy compatibile con vecchi punti del codice
        che chiamano throttle.update(...).
        """
        api_calls_min = kwargs.get("api_calls_min")
        if api_calls_min is not None:
            try:
                self._last_rate = float(api_calls_min)
            except Exception:
                self._last_rate = 0.0
        return None

    def reset(self):
        """Metodo legacy compatibile."""
        self._last_rate = 0.0
        self._blocked = False

    def is_blocked(self):
        """Metodo legacy compatibile."""
        return self._blocked