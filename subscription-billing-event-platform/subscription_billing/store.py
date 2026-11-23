"""Entitlement store — DynamoDB-shaped key-value table.

Partition key: (partner_id, subscriber_id). Sort key: subscription_id.
Each item carries a version (optimistic locking), a status, a price in
minor units, a billing period, and an optional expiry (TTL, epoch seconds).

Conditional writes fail instead of silently overwriting: provisioning an
already-active subscription for the same partner/subscriber/plan returns
the existing item, and updates require the expected version.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Entitlement:
    partner_id: str
    subscriber_id: str
    subscription_id: str
    plan_id: str
    status: str  # active | trialing | past_due | cancelled | expired
    price_minor: int  # price in minor currency units, e.g. cents
    currency: str = "USD"
    period_start: int = 0  # epoch seconds
    period_end: int = 0
    version: int = 1
    created_at: int = field(default_factory=lambda: int(time.time()))

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.partner_id, self.subscriber_id, self.subscription_id)

    def is_expired(self, now: int | None = None) -> bool:
        now = int(time.time()) if now is None else now
        return self.period_end > 0 and now > self.period_end


class ConditionalWriteError(Exception):
    """Raised when a conditional write's predicate does not hold."""


class EntitlementStore:
    """In-memory DynamoDB-shaped table for subscription entitlements."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], Entitlement] = {}

    def put(self, item: Entitlement, *, condition: str | None = None,
            expected_version: int | None = None) -> Entitlement:
        """Store an item.

        condition="not_exists" fails if the key already exists.
        expected_version fails unless the stored item has that version.
        """
        existing = self._items.get(item.key)
        if condition == "not_exists" and existing is not None:
            raise ConditionalWriteError(f"item already exists: {item.key}")
        if expected_version is not None:
            if existing is None:
                raise ConditionalWriteError(f"no item to update: {item.key}")
            if existing.version != expected_version:
                raise ConditionalWriteError(
                    f"version mismatch for {item.key}: expected "
                    f"{expected_version}, found {existing.version}")
            item.version = existing.version + 1
        self._items[item.key] = item
        return item

    def get(self, partner_id: str, subscriber_id: str,
            subscription_id: str) -> Entitlement | None:
        return self._items.get((partner_id, subscriber_id, subscription_id))

    def query_subscriber(self, partner_id: str, subscriber_id: str,
                         *, now: int | None = None) -> list[Entitlement]:
        """All entitlements for one subscriber, expired ones excluded."""
        out = [e for (p, s, _), e in self._items.items()
               if p == partner_id and s == subscriber_id]
        if now is not None:
            out = [e for e in out if not e.is_expired(now)]
        return sorted(out, key=lambda e: e.subscription_id)

    def query_partner(self, partner_id: str) -> list[Entitlement]:
        return sorted(
            (e for (p, _, _), e in self._items.items() if p == partner_id),
            key=lambda e: (e.subscriber_id, e.subscription_id))

    def count_active(self, partner_id: str, *, now: int | None = None) -> int:
        return sum(1 for e in self.query_partner(partner_id)
                   if e.status == "active" and not e.is_expired(now))

    def __len__(self) -> int:
        return len(self._items)
