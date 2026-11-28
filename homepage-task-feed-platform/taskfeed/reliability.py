"""Reliability: retries, circuit breaker, and safe action replay.

A flaky source gets bounded retries with exponential backoff (the sleep is
injectable so tests run instantly). A source that keeps failing trips a
circuit breaker: calls fail fast until the cooldown passes, then one probe
is allowed through (half-open) before the breaker closes again.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


def retry_with_backoff(fn, *, max_attempts: int = 3, base_delay_s: float = 0.1,
                       sleep=time.sleep):
    """Call fn(); retry on exception with exponential backoff. Returns (value, attempts)."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except Exception as exc:  # noqa: BLE001 - retry boundary is the point
            last_exc = exc
            if attempt < max_attempts:
                sleep(base_delay_s * (2 ** (attempt - 1)))
    raise last_exc  # type: ignore[misc]


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_s: float = 60.0
    _failures: int = 0
    _opened_at: float | None = None
    _half_open_probe_in_flight: bool = False

    def allow(self, now_s: float) -> bool:
        if self._opened_at is None:
            return True
        if now_s - self._opened_at >= self.cooldown_s:
            if not self._half_open_probe_in_flight:
                self._half_open_probe_in_flight = True
                return True
            return False
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._half_open_probe_in_flight = False

    def record_failure(self, now_s: float) -> None:
        self._failures += 1
        self._half_open_probe_in_flight = False
        if self._failures >= self.failure_threshold:
            self._opened_at = now_s

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None

    @property
    def failures(self) -> int:
        return self._failures
