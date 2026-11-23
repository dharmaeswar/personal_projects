"""In-memory store: aggregates, the outbox, idempotency records, audit trail.

Kept deliberately simple (plain dicts/lists) so the service logic and the
outbox semantics are easy to test without a database. A real deployment
would swap this for a transactional store; the service only depends on the
methods below, so the swap is a one-file change.
"""

from __future__ import annotations

from .models import AuditEntry, CarePlan, Event, Referral, Suggestion, Task


class Store:
    def __init__(self):
        self.plans: dict[str, CarePlan] = {}
        self.referrals: dict[str, Referral] = {}
        self.tasks: dict[str, Task] = {}
        self.outbox: list[Event] = []
        self.audit: list[AuditEntry] = []
        # Idempotency keys of events already handled, so a redelivered
        # event is recognised and skipped instead of applied twice.
        self.processed_keys: set[str] = set()
        # Idempotency keys of write requests already applied, so a retried
        # client call returns the original result instead of duplicating it.
        self.request_keys: dict[str, dict] = {}
        # Agent-assist suggestions, keyed by suggestion id. A suggestion
        # never changes plan state until a human approves it.
        self.suggestions: dict[str, Suggestion] = {}

    # -- aggregates -----------------------------------------------------
    def save_plan(self, plan: CarePlan) -> None:
        self.plans[plan.id] = plan

    def save_referral(self, referral: Referral) -> None:
        self.referrals[referral.id] = referral

    def save_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    # -- outbox ---------------------------------------------------------
    def enqueue(self, event: Event) -> None:
        self.outbox.append(event)

    def pending_events(self) -> list[Event]:
        return [e for e in self.outbox if not e.delivered]

    # -- audit ----------------------------------------------------------
    def record_audit(self, entry: AuditEntry) -> None:
        self.audit.append(entry)

    def audit_for(self, aggregate_id: str) -> list[AuditEntry]:
        return [a for a in self.audit if a.aggregate_id == aggregate_id]
