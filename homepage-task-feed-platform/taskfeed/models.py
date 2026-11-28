"""Core models for the Homepage task-feed platform.

A task is one actionable item surfaced on the Homepage feed. Tasks come from
many product teams (approvals, receipts, account setup, recommendations) and
must all behave the same way in the feed: one rank, one set of standard
actions, one detail view shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

TASK_KINDS = ("approval", "receipt", "setup", "recommendation", "alert")

# States a task can be in. Terminal states are actioned and dismissed.
TASK_STATES = ("open", "snoozed", "actioned", "dismissed")

# The standard actions every task in the feed supports, whatever its source.
STANDARD_ACTIONS = ("approve", "reject", "complete", "dismiss", "snooze", "open_detail")

# Which actions are valid for each task kind. Every kind supports dismiss,
# snooze and open_detail; approvals add approve/reject; the rest add complete.
KIND_ACTIONS = {
    "approval": ("approve", "reject", "dismiss", "snooze", "open_detail"),
    "receipt": ("complete", "dismiss", "snooze", "open_detail"),
    "setup": ("complete", "dismiss", "snooze", "open_detail"),
    "recommendation": ("complete", "dismiss", "snooze", "open_detail"),
    "alert": ("complete", "dismiss", "snooze", "open_detail"),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Task:
    """One actionable item from one product team."""

    source: str            # producing team, e.g. "approvals"
    external_id: str       # stable id inside the source team
    title: str
    kind: str              # one of TASK_KINDS
    priority: int          # 1 (low) .. 5 (urgent)
    created_at: datetime
    due_at: datetime | None = None
    owner: str = ""        # user the task is for
    relevance: float = 0.5  # 0..1, how relevant the source thinks it is
    payload: dict = field(default_factory=dict)
    state: str = "open"
    updated_at: datetime | None = None
    stale: bool = False    # True when served from cache after a source failure
    snoozed_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind not in TASK_KINDS:
            raise ValueError(f"unknown task kind: {self.kind!r}")
        if not 1 <= self.priority <= 5:
            raise ValueError(f"priority must be 1..5, got {self.priority}")
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError(f"relevance must be 0..1, got {self.relevance}")
        if self.state not in TASK_STATES:
            raise ValueError(f"unknown task state: {self.state!r}")
        if self.updated_at is None:
            self.updated_at = self.created_at

    @property
    def key(self) -> tuple[str, str]:
        """Identity of a task across fetches: (source, external_id)."""
        return (self.source, self.external_id)

    def is_overdue(self, now: datetime) -> bool:
        return self.due_at is not None and self.due_at < now and self.state == "open"

    def allowed_actions(self) -> tuple[str, ...]:
        return KIND_ACTIONS[self.kind]


@dataclass
class DetailView:
    """The standard detail view every task opens into.

    Same shape for every kind so the frontend renders one component:
    a title, a list of labelled fields, and the actions available.
    """

    task_key: tuple[str, str]
    title: str
    fields: list[tuple[str, str]]  # (label, value) rows, in display order
    actions: tuple[str, ...]
    source: str
