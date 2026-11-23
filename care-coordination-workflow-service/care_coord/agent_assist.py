"""AI-agent assist for the care-coordination workflow service.

A deterministic, rule-based suggestion engine that plays the role of an
AI agent partner: it reads a care plan's state and proposes next steps —
follow up a stalled referral, escalate a blocked task, complete a plan
whose work is done, review a plan left on hold. The rules are transparent
and testable; there are no network calls, no model calls, and no real
data involved.

Nothing is applied automatically. Every suggestion stays ``proposed``
until a human operator approves or rejects it, and the decision — who
decided, what they decided, why — is written to the same audit trail as
every other mutation. Approving a suggestion applies it through the
normal service methods, so state machines, outbox events and idempotency
all still hold.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    PlanStatus,
    ReferralStatus,
    Suggestion,
    TaskStatus,
    now_iso,
)
from .service import CareCoordinationService, InvalidTransitionError

# A referral still only "requested" this many days after it was created
# counts as stalled and earns a follow-up suggestion.
DEFAULT_STALE_DAYS = 7


class SuggestionNotFoundError(KeyError):
    pass


class SuggestionDecidedError(ValueError):
    pass


def _age_days(created_at: str, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).total_seconds() / 86400.0


class AgentAssist:
    """Proposes next steps for a care plan; a human decides each one."""

    def __init__(self, service: CareCoordinationService, stale_days: int = DEFAULT_STALE_DAYS):
        self.service = service
        self.store = service.store
        self.stale_days = stale_days

    # -- proposing ------------------------------------------------------
    def suggest_for_plan(self, plan_id: str, now: datetime | None = None) -> list[Suggestion]:
        """Evaluate the rules for one plan; return its open suggestions.

        New suggestions are stored; an open suggestion for the same plan
        and kind is returned as-is instead of duplicated.
        """
        plan = self.service.get_care_plan(plan_id)
        now = now or datetime.now(timezone.utc)
        referrals = [r for r in self.store.referrals.values() if r.plan_id == plan_id]
        tasks = [t for t in self.store.tasks.values() if t.plan_id == plan_id]

        def _propose(kind, summary, rationale, action):
            for existing in self.store.suggestions.values():
                if (existing.plan_id == plan_id and existing.kind == kind
                        and existing.status == "proposed"
                        and existing.proposed_action == action):
                    return existing
            suggestion = Suggestion(
                plan_id=plan_id, kind=kind, summary=summary,
                rationale=rationale, proposed_action=action)
            self.store.suggestions[suggestion.id] = suggestion
            return suggestion

        if plan.status is PlanStatus.ACTIVE:
            for ref in referrals:
                if ref.status is ReferralStatus.REQUESTED:
                    age = _age_days(ref.created_at, now)
                    if age >= self.stale_days:
                        _propose(
                            "follow_up_referral",
                            f"Follow up on the {ref.specialty} referral",
                            f"Referral {ref.id[:6]} has sat in 'requested' for "
                            f"{age:.0f} days with no acceptance.",
                            {"action": "create_task",
                             "title": f"Follow up on {ref.specialty} referral",
                             "assignee": "care-team-1",
                             "referral_id": ref.id})
            for task in tasks:
                if task.status is TaskStatus.BLOCKED:
                    _propose(
                        "escalate_blocked_task",
                        f"Escalate blocked task: {task.title}",
                        f"Task {task.id[:6]} is blocked; the plan cannot move "
                        f"until someone unblocks it.",
                        {"action": "create_task",
                         "title": f"Escalate blocked task: {task.title}",
                         "assignee": "care-team-1",
                         "task_id": task.id})
            open_refs = [r for r in referrals if r.status not in
                         {ReferralStatus.COMPLETED, ReferralStatus.DECLINED, ReferralStatus.CANCELLED}]
            open_tasks = [t for t in tasks if t.status not in
                          {TaskStatus.DONE, TaskStatus.CANCELLED}]
            if referrals and tasks and not open_refs and not open_tasks:
                _propose(
                    "complete_plan",
                    "Complete the plan — all referrals and tasks are finished",
                    f"All {len(referrals)} referrals and {len(tasks)} tasks are "
                    f"in terminal states; the plan is ready to close.",
                    {"action": "complete_plan"})

        if plan.status is PlanStatus.ON_HOLD:
            open_refs = [r for r in referrals if r.status not in
                         {ReferralStatus.COMPLETED, ReferralStatus.DECLINED, ReferralStatus.CANCELLED}]
            open_tasks = [t for t in tasks if t.status not in
                          {TaskStatus.DONE, TaskStatus.CANCELLED}]
            if not open_refs and not open_tasks:
                _propose(
                    "review_on_hold",
                    "Review this on-hold plan: resume it or cancel it",
                    "The plan is on hold with nothing open; it needs a "
                    "human call on whether it still matters.",
                    {"action": "create_task",
                     "title": "Review on-hold plan: resume or cancel",
                     "assignee": "care-team-1"})

        return [s for s in self.store.suggestions.values()
                if s.plan_id == plan_id and s.status == "proposed"]

    # -- deciding -------------------------------------------------------
    def list_suggestions(self, plan_id: str | None = None,
                         status: str | None = None) -> list[Suggestion]:
        out = list(self.store.suggestions.values())
        if plan_id is not None:
            out = [s for s in out if s.plan_id == plan_id]
        if status is not None:
            out = [s for s in out if s.status == status]
        return out

    def approve(self, suggestion_id: str, actor: str = "coordinator"):
        """Apply a proposed suggestion through the service. Human only."""
        suggestion = self.store.suggestions.get(suggestion_id)
        if suggestion is None:
            raise SuggestionNotFoundError(suggestion_id)
        if suggestion.status != "proposed":
            raise SuggestionDecidedError(
                f"suggestion {suggestion_id} is already {suggestion.status}")
        action = suggestion.proposed_action
        if action.get("action") == "create_task":
            self.service.create_task(
                suggestion.plan_id, action["title"],
                assignee=action.get("assignee", ""), actor=actor)
        elif action.get("action") == "complete_plan":
            self.service.transition_plan(
                suggestion.plan_id, PlanStatus.COMPLETED, actor=actor)
        else:
            raise InvalidTransitionError(
                f"unknown proposed action: {action.get('action')!r}")
        suggestion.status = "approved"
        suggestion.decided_by = actor
        suggestion.decided_at = now_iso()
        self.store.record_audit(_audit_entry(
            actor, "agent_suggestion.approved", "suggestion", suggestion.id,
            f"{suggestion.kind}: {suggestion.summary}"))
        return suggestion

    def reject(self, suggestion_id: str, actor: str = "coordinator",
               reason: str = ""):
        """Decline a proposed suggestion. Nothing is applied."""
        suggestion = self.store.suggestions.get(suggestion_id)
        if suggestion is None:
            raise SuggestionNotFoundError(suggestion_id)
        if suggestion.status != "proposed":
            raise SuggestionDecidedError(
                f"suggestion {suggestion_id} is already {suggestion.status}")
        suggestion.status = "rejected"
        suggestion.decided_by = actor
        suggestion.decided_at = now_iso()
        suggestion.decision_reason = reason
        self.store.record_audit(_audit_entry(
            actor, "agent_suggestion.rejected", "suggestion", suggestion.id,
            f"{suggestion.kind}: {suggestion.summary}"
            + (f" — {reason}" if reason else "")))
        return suggestion


def _audit_entry(actor, action, agg_type, agg_id, detail):
    from .models import AuditEntry

    return AuditEntry(actor=actor, action=action, aggregate_type=agg_type,
                      aggregate_id=agg_id, detail=detail)
