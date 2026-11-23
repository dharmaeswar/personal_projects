"""Domain models for the care-coordination workflow service.

All data is synthetic and de-identified by design: patient references are
opaque synthetic IDs (``PAT-0001`` style), never names, dates of birth, or
any real health record. This module holds no network or I/O code.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReferralStatus(str, enum.Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


# Allowed state transitions. Anything else is rejected by the service.
PLAN_TRANSITIONS = {
    PlanStatus.DRAFT: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.ACTIVE: {PlanStatus.ON_HOLD, PlanStatus.COMPLETED, PlanStatus.CANCELLED},
    PlanStatus.ON_HOLD: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.COMPLETED: set(),
    PlanStatus.CANCELLED: set(),
}

REFERRAL_TRANSITIONS = {
    ReferralStatus.REQUESTED: {ReferralStatus.ACCEPTED, ReferralStatus.DECLINED, ReferralStatus.CANCELLED},
    ReferralStatus.ACCEPTED: {ReferralStatus.SCHEDULED, ReferralStatus.CANCELLED},
    ReferralStatus.SCHEDULED: {ReferralStatus.COMPLETED, ReferralStatus.CANCELLED},
    ReferralStatus.COMPLETED: set(),
    ReferralStatus.DECLINED: set(),
    ReferralStatus.CANCELLED: set(),
}

TASK_TRANSITIONS = {
    TaskStatus.OPEN: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class CarePlan:
    id: str = field(default_factory=new_id)
    patient_ref: str = ""
    title: str = ""
    goals: list = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Referral:
    id: str = field(default_factory=new_id)
    plan_id: str = ""
    specialty: str = ""
    reason: str = ""
    status: ReferralStatus = ReferralStatus.REQUESTED
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Task:
    id: str = field(default_factory=new_id)
    plan_id: str = ""
    title: str = ""
    assignee: str = ""
    status: TaskStatus = TaskStatus.OPEN
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Event:
    """A domain event waiting in the outbox (or already delivered)."""

    id: str = field(default_factory=new_id)
    event_type: str = ""
    aggregate_id: str = ""
    payload: dict = field(default_factory=dict)
    idempotency_key: str = ""
    attempts: int = 0
    delivered: bool = False
    created_at: str = field(default_factory=now_iso)

    def __post_init__(self):
        if not self.idempotency_key:
            self.idempotency_key = f"{self.event_type}:{self.aggregate_id}:{self.id}"


@dataclass
class Suggestion:
    """A proposed next step from the agent-assist engine.

    ``kind`` names the rule that fired; ``proposed_action`` is a small
    dict the engine would apply on approval, e.g.
    ``{"action": "create_task", "title": ..., "assignee": ...}`` or
    ``{"action": "complete_plan"}``. ``status`` moves proposed ->
    approved / rejected only through a human decision; nothing here
    changes plan state on its own.
    """

    id: str = field(default_factory=new_id)
    plan_id: str = ""
    kind: str = ""
    summary: str = ""
    rationale: str = ""
    proposed_action: dict = field(default_factory=dict)
    status: str = "proposed"
    created_at: str = field(default_factory=now_iso)
    decided_by: str = ""
    decided_at: str = ""
    decision_reason: str = ""


@dataclass
class AuditEntry:
    id: str = field(default_factory=new_id)
    actor: str = "system"
    action: str = ""
    aggregate_type: str = ""
    aggregate_id: str = ""
    detail: str = ""
    created_at: str = field(default_factory=now_iso)
