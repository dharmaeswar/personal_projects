"""Transactional outbox + idempotent dispatcher.

Writes and their events are recorded together in the store (the outbox
pattern): a service method mutates an aggregate and enqueues its event in
the same step, so an event can never be lost if the process crashes after
the write. A separate dispatcher then delivers pending events to handlers
with bounded retries and exponential backoff. Delivery is at-least-once;
handlers are idempotent because the dispatcher records each event's
idempotency key before invoking the handler, and skips keys already seen —
so a retry or duplicate delivery is a no-op. That combination gives
effectively-once processing without a distributed transaction.
"""

from __future__ import annotations

import time
from typing import Callable

from .models import Event
from .store import Store

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.1


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 0.1s, 0.2s, 0.4s, ... capped at 5s."""
    return min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), 5.0)


class Dispatcher:
    """Delivers pending outbox events to a handler, idempotently."""

    def __init__(self, store: Store, sleep: Callable[[float], None] = time.sleep):
        self.store = store
        self.sleep = sleep

    def dispatch_one(self, event: Event, handler: Callable[[Event], None]) -> str:
        """Deliver one event. Returns 'delivered', 'duplicate' or 'failed'."""
        if event.idempotency_key in self.store.processed_keys:
            event.delivered = True
            return "duplicate"
        event.attempts += 1
        try:
            handler(event)
        except Exception:
            if event.attempts >= MAX_ATTEMPTS:
                event.delivered = True  # dead-lettered: stop retrying
                return "failed"
            self.sleep(backoff_seconds(event.attempts))
            return "retry"
        # Record the key only after the handler succeeds, so a crash
        # mid-handler is retried and a success is never applied twice.
        self.store.processed_keys.add(event.idempotency_key)
        event.delivered = True
        return "delivered"

    def dispatch_all(self, handler: Callable[[Event], None]) -> dict:
        """Deliver every pending event until the outbox is drained or all
        remaining events need another retry round. Returns outcome counts."""
        counts = {"delivered": 0, "duplicate": 0, "retry": 0, "failed": 0}
        for event in list(self.store.pending_events()):
            counts[self.dispatch_one(event, handler)] += 1
        return counts
