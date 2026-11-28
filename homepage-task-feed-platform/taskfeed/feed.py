"""Feed: build one ranked, actionable Homepage feed from many sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .actions import ActionLog
from .ingest import ingest
from .latency import LatencyTracker, SourceCache, SourceResult, fetch_with_budget
from .models import Task
from .ranking import rank, score


@dataclass
class FeedResponse:
    tasks: list[Task]
    scores: dict[tuple[str, str], float]
    sources: list[SourceResult]
    notices: list[str] = field(default_factory=list)
    stale_count: int = 0

    def top(self, n: int = 5) -> list[Task]:
        return self.tasks[:n]


class FeedBuilder:
    """Owns per-source caches, latency tracking and the action log."""

    def __init__(self, budget_ms: float = 250.0) -> None:
        self.budget_ms = budget_ms
        self.cache = SourceCache()
        self.tracker = LatencyTracker()
        self.actions = ActionLog()

    def build(
        self,
        fetchers: dict[str, callable],
        *,
        user: str,
        now: datetime,
        limit: int = 50,
    ) -> FeedResponse:
        """Fetch every source inside budget, dedupe, rank, return the feed."""
        results: list[SourceResult] = []
        raw: list[dict] = []
        for source, fetch_fn in fetchers.items():
            res = fetch_with_budget(source, fetch_fn, self.budget_ms, self.cache, self.tracker)
            results.append(res)
            for t in res.tasks:
                raw.append({
                    "source": t.source,
                    "external_id": t.external_id,
                    "title": t.title,
                    "kind": t.kind,
                    "priority": t.priority,
                    "created_at": t.created_at.isoformat(),
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                    "owner": t.owner,
                    "relevance": t.relevance,
                    "payload": t.payload,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    "stale": t.stale,
                })
        # Wake snoozed tasks whose snooze expired before ranking.
        ingested = ingest(raw)
        self.actions.wake_snoozed(ingested.tasks, now)
        visible = [t for t in ingested.tasks if t.state == "open"]
        ranked = rank(visible, now)[:limit]
        return FeedResponse(
            tasks=ranked,
            scores={t.key: score(t, now) for t in ranked},
            sources=results,
            notices=[r.notice for r in results if r.notice],
            stale_count=sum(1 for t in ranked if t.stale),
        )
