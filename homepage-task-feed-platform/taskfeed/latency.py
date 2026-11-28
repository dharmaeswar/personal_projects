"""Latency budgets and graceful degradation.

Each source gets a latency budget for a feed build. A source that answers
inside budget is "ok"; one that answers late is "degraded" and the feed
serves its last cached tasks flagged stale; one that fails outright is
"failed" and contributes nothing, with a notice. p95 tracking shows which
sources are trending slow before they blow the budget.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .models import Task


@dataclass
class SourceResult:
    source: str
    status: str  # "ok" | "degraded" | "failed"
    tasks: list[Task] = field(default_factory=list)
    latency_ms: float = 0.0
    notice: str = ""


class LatencyTracker:
    """Rolling p50/p95 per source over the last N samples."""

    def __init__(self, window: int = 100) -> None:
        self.window = window
        self._samples: dict[str, list[float]] = {}

    def record(self, source: str, latency_ms: float) -> None:
        samples = self._samples.setdefault(source, [])
        samples.append(latency_ms)
        if len(samples) > self.window:
            del samples[: len(samples) - self.window]

    def p95(self, source: str) -> float | None:
        samples = self._samples.get(source, [])
        if not samples:
            return None
        if len(samples) == 1:
            return samples[0]
        return statistics.quantiles(samples, n=20, method="inclusive")[18]

    def p50(self, source: str) -> float | None:
        samples = self._samples.get(source, [])
        if not samples:
            return None
        return statistics.median(samples)


class SourceCache:
    """Last good tasks per source, served stale when a source degrades."""

    def __init__(self) -> None:
        self._cache: dict[str, list[Task]] = {}

    def store(self, source: str, tasks: list[Task]) -> None:
        self._cache[source] = list(tasks)

    def stale_tasks(self, source: str) -> list[Task]:
        out = []
        for t in self._cache.get(source, []):
            stale = Task(
                source=t.source,
                external_id=t.external_id,
                title=t.title,
                kind=t.kind,
                priority=t.priority,
                created_at=t.created_at,
                due_at=t.due_at,
                owner=t.owner,
                relevance=t.relevance,
                payload=dict(t.payload),
                state=t.state,
                updated_at=t.updated_at,
                stale=True,
            )
            out.append(stale)
        return out

    def has(self, source: str) -> bool:
        return source in self._cache


def fetch_with_budget(
    source: str,
    fetch_fn,
    budget_ms: float,
    cache: SourceCache,
    tracker: LatencyTracker,
) -> SourceResult:
    """Call fetch_fn() -> (tasks, latency_ms); enforce the budget.

    fetch_fn returning tasks slower than the budget still yields its tasks
    only if a cache exists to mark stale; the slow answer itself is dropped
    so one slow team cannot stall the feed.
    """
    try:
        tasks, latency_ms = fetch_fn()
    except Exception as exc:  # source down: degrade to cache or fail cleanly
        tracker.record(source, budget_ms)
        if cache.has(source):
            return SourceResult(
                source, "degraded", cache.stale_tasks(source), budget_ms,
                notice=f"{source} failed ({exc}); showing cached tasks",
            )
        return SourceResult(source, "failed", [], budget_ms, notice=f"{source} failed ({exc})")
    tracker.record(source, latency_ms)
    if latency_ms <= budget_ms:
        cache.store(source, tasks)
        return SourceResult(source, "ok", tasks, latency_ms)
    if cache.has(source):
        return SourceResult(
            source, "degraded", cache.stale_tasks(source), latency_ms,
            notice=f"{source} answered in {latency_ms:.0f}ms, over the {budget_ms:.0f}ms budget; showing cached tasks",
        )
    return SourceResult(
        source, "degraded", [], latency_ms,
        notice=f"{source} answered in {latency_ms:.0f}ms, over the {budget_ms:.0f}ms budget; no cache yet",
    )
