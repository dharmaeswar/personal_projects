"""Retry with backoff and a circuit breaker.

These are the resilience primitives the dispatch path uses when it calls
a partner scheduling system: a transient failure is retried, a persistently
failing partner trips the breaker so the caller fails fast instead of
queuing up behind a dead dependency, and the breaker half-opens after a
cooldown to probe recovery.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class CircuitOpenError(RuntimeError):
    pass


def retry_call(fn, max_attempts: int = 3, base_delay_s: float = 0.1,
               sleep=time.sleep):
    """Call fn(); retry on Exception with exponential backoff.

    Returns (result, attempts_used). Raises the last error after the
    final attempt. ``sleep`` is injectable so tests run without waiting.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except Exception as exc:  # noqa: BLE001 - retry any transient error
            last_error = exc
            if attempt < max_attempts:
                sleep(base_delay_s * (2 ** (attempt - 1)))
    raise last_error  # type: ignore[misc]


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_timeout_s: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _half_open_probe: bool = field(default=False, init=False)

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self.reset_timeout_s:
            return "half-open"
        return "open"

    def call(self, fn, *args, **kwargs):
        if self.state == "open":
            raise CircuitOpenError("circuit breaker is open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()
                self._half_open_probe = False
            raise
        self._failures = 0
        self._opened_at = None
        return result

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
