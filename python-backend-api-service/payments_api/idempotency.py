"""Idempotency store and retry helper for the payments service.

Idempotency: a client that retries a checkout with the same
Idempotency-Key must get the original response, never a second loan.
Retry: a downstream call (here a simulated ledger write) is retried with
exponential backoff and a bounded number of attempts.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class IdempotencyStore:
    """Thread-safe in-memory map of idempotency key -> stored response."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._responses: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        with self._lock:
            stored = self._responses.get(key)
            return dict(stored) if stored is not None else None

    def put(self, key: str, response: dict) -> None:
        with self._lock:
            self._responses.setdefault(key, dict(response))

    def __len__(self) -> int:
        with self._lock:
            return len(self._responses)


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay_s: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn, retrying transient errors with exponential backoff.

    Only RuntimeError is treated as transient here (the simulated ledger
    raises it). Other exceptions propagate immediately. Delays are
    base, 2x base, 4x base ... up to max_attempts - 1 sleeps.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except RuntimeError:
            if attempt >= max_attempts:
                raise
            sleep(base_delay_s * (2 ** (attempt - 1)))


class SimulatedLedger:
    """Stand-in for a downstream ledger service.

    Fails the first `fail_times` calls with a transient error, then
    succeeds. Lets tests exercise the retry path without a real service.
    Nothing here touches real money or a real ledger.
    """

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def record_loan(self, loan_id: str) -> dict:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("ledger temporarily unavailable")
        return {"loan_id": loan_id, "ledger_status": "recorded"}
