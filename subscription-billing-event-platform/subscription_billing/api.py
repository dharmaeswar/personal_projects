"""Entitlement lookup — low-latency read path.

Builds an in-memory index over the entitlement store so a partner can
check "does this subscriber have an active subscription to this plan?"
in microseconds instead of scanning the table. Latency samples are
recorded so p50/p95 can be reported, the way a low-latency service
would track its read path.
"""

from __future__ import annotations

import time

from .store import Entitlement, EntitlementStore


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(len(sorted_samples) - 1,
              max(0, int(pct / 100 * len(sorted_samples))))
    return sorted_samples[idx]


class EntitlementLookup:
    def __init__(self, store: EntitlementStore) -> None:
        self.store = store
        # (partner_id, subscriber_id, plan_id) -> Entitlement
        self._index: dict[tuple[str, str, str], Entitlement] = {}
        self._latencies_us: list[float] = []
        self.rebuild()

    def rebuild(self) -> None:
        self._index = {
            (e.partner_id, e.subscriber_id, e.plan_id): e
            for e in self.store._items.values()
        }

    def has_active(self, partner_id: str, subscriber_id: str,
                   plan_id: str, *, now: int | None = None) -> bool:
        start = time.perf_counter_ns()
        item = self._index.get((partner_id, subscriber_id, plan_id))
        ok = bool(item and item.status == "active"
                  and not item.is_expired(now))
        self._latencies_us.append((time.perf_counter_ns() - start) / 1000)
        return ok

    def latency_stats_us(self) -> dict[str, float]:
        samples = sorted(self._latencies_us)
        if not samples:
            return {"count": 0, "p50_us": 0.0, "p95_us": 0.0, "max_us": 0.0}
        return {"count": len(samples),
                "p50_us": _percentile(samples, 50),
                "p95_us": _percentile(samples, 95),
                "max_us": samples[-1]}
