"""Care-coordination workflow service: care plans, referrals, tasks.

State machines are enforced on every transition (see models.py for the
allowed-transition tables). Every mutation writes an audit entry and
enqueues a domain event in the same step (transactional outbox), so the
audit trail and the event stream can never drift apart from the data.

Write methods accept an optional ``request_key``: if a client retries a
request with the same key, the original result is returned and nothing is
applied twice — the same idempotency idea as the event dispatcher, applied
to the API surface.
"""

from __future__ import annotations

from .events import Dispatcher
from .models import (
    PLAN_TRANSITIONS,
    REFERRAL_TRANSITIONS,
    TASK_TRANSITIONS,
    AuditEntry,
    CarePlan,
    Event,
    PlanStatus,
    Referral,
    ReferralStatus,
    Task,
    TaskStatus,
    now_iso,
)
from .store import Store

TERMINAL_REFERRAL = {ReferralStatus.COMPLETED, ReferralStatus.DECLINED, ReferralStatus.CANCELLED}
TERMINAL_TASK = {TaskStatus.DONE, TaskStatus.CANCELLED}


class NotFoundError(KeyError):
    pass


class InvalidTransitionError(ValueError):
    pass


class ValidationError(ValueError):
    pass


class CareCoordinationService:
    def __init__(self, store: Store | None = None):
        self.store = store or Store()
        self.dispatcher = Dispatcher(self.store)

    # -- helpers --------------------------------------------------------
    def _audit(self, actor, action, agg_type, agg_id, detail):
        self.store.record_audit(
            AuditEntry(actor=actor, action=action, aggregate_type=agg_type,
                       aggregate_id=agg_id, detail=detail)
        )

    def _emit(self, event_type, aggregate_id, payload, request_key=None):
        key = request_key or ""
        event = Event(event_type=event_type, aggregate_id=aggregate_id,
                      payload=payload, idempotency_key=key or None)
        self.store.enqueue(event)
        return event

    def _idempotent_write(self, request_key, fn):
        """Run fn() once per request_key; return the cached result on retry."""
        if request_key and request_key in self.store.request_keys:
            return self.store.request_keys[request_key]
        result = fn()
        if request_key:
            self.store.request_keys[request_key] = result
        return result

    # -- care plans -----------------------------------------------------
    def create_care_plan(self, patient_ref, title, goals=None, actor="coordinator",
                         request_key=None):
        if not patient_ref or not title:
            raise ValidationError("patient_ref and title are required")
        if goals is None:
            goals = []

        def _do():
            plan = CarePlan(patient_ref=patient_ref, title=title, goals=list(goals))
            self.store.save_plan(plan)
            self._audit(actor, "care_plan.created", "care_plan", plan.id,
                        f"title={title!r} goals={len(goals)}")
            self._emit("care_plan.created", plan.id,
                       {"patient_ref": patient_ref, "title": title}, request_key)
            return plan

        return self._idempotent_write(request_key, _do)

    def get_care_plan(self, plan_id):
        plan = self.store.plans.get(plan_id)
        if plan is None:
            raise NotFoundError(plan_id)
        return plan

    def transition_plan(self, plan_id, new_status, actor="coordinator"):
        plan = self.get_care_plan(plan_id)
        new_status = PlanStatus(new_status)
        if new_status not in PLAN_TRANSITIONS[plan.status]:
            raise InvalidTransitionError(
                f"plan {plan_id}: {plan.status.value} -> {new_status.value} is not allowed")
        if new_status is PlanStatus.COMPLETED:
            open_refs = [r for r in self.store.referrals.values()
                         if r.plan_id == plan_id and r.status not in TERMINAL_REFERRAL]
            open_tasks = [t for t in self.store.tasks.values()
                          if t.plan_id == plan_id and t.status not in TERMINAL_TASK]
            if open_refs or open_tasks:
                raise InvalidTransitionError(
                    f"plan {plan_id} has {len(open_refs)} open referrals and "
                    f"{len(open_tasks)} open tasks; complete them first")
        old = plan.status
        plan.status = new_status
        plan.updated_at = now_iso()
        self._audit(actor, "care_plan.transition", "care_plan", plan.id,
                    f"{old.value} -> {new_status.value}")
        self._emit("care_plan.transitioned", plan.id,
                   {"from": old.value, "to": new_status.value})
        return plan

    # -- referrals ------------------------------------------------------
    def add_referral(self, plan_id, specialty, reason="", actor="coordinator",
                     request_key=None):
        plan = self.get_care_plan(plan_id)
        if plan.status in (PlanStatus.COMPLETED, PlanStatus.CANCELLED):
            raise InvalidTransitionError(f"plan {plan_id} is {plan.status.value}; no new referrals")
        if not specialty:
            raise ValidationError("specialty is required")

        def _do():
            ref = Referral(plan_id=plan_id, specialty=specialty, reason=reason)
            self.store.save_referral(ref)
            self._audit(actor, "referral.requested", "referral", ref.id,
                        f"specialty={specialty!r} plan={plan_id}")
            self._emit("referral.requested", ref.id,
                       {"plan_id": plan_id, "specialty": specialty}, request_key)
            return ref

        return self._idempotent_write(request_key, _do)

    def transition_referral(self, referral_id, new_status, actor="coordinator"):
        ref = self.store.referrals.get(referral_id)
        if ref is None:
            raise NotFoundError(referral_id)
        new_status = ReferralStatus(new_status)
        if new_status not in REFERRAL_TRANSITIONS[ref.status]:
            raise InvalidTransitionError(
                f"referral {referral_id}: {ref.status.value} -> {new_status.value} is not allowed")
        old = ref.status
        ref.status = new_status
        ref.updated_at = now_iso()
        self._audit(actor, "referral.transition", "referral", ref.id,
                    f"{old.value} -> {new_status.value}")
        self._emit("referral.transitioned", ref.id,
                   {"from": old.value, "to": new_status.value})
        return ref

    # -- tasks ----------------------------------------------------------
    def create_task(self, plan_id, title, assignee="", actor="coordinator",
                    request_key=None):
        plan = self.get_care_plan(plan_id)
        if plan.status in (PlanStatus.COMPLETED, PlanStatus.CANCELLED):
            raise InvalidTransitionError(f"plan {plan_id} is {plan.status.value}; no new tasks")
        if not title:
            raise ValidationError("title is required")

        def _do():
            task = Task(plan_id=plan_id, title=title, assignee=assignee)
            self.store.save_task(task)
            self._audit(actor, "task.created", "task", task.id,
                        f"title={title!r} assignee={assignee!r}")
            self._emit("task.created", task.id,
                       {"plan_id": plan_id, "title": title}, request_key)
            return task

        return self._idempotent_write(request_key, _do)

    def transition_task(self, task_id, new_status, actor="coordinator"):
        task = self.store.tasks.get(task_id)
        if task is None:
            raise NotFoundError(task_id)
        new_status = TaskStatus(new_status)
        if new_status not in TASK_TRANSITIONS[task.status]:
            raise InvalidTransitionError(
                f"task {task_id}: {task.status.value} -> {new_status.value} is not allowed")
        old = task.status
        task.status = new_status
        task.updated_at = now_iso()
        self._audit(actor, "task.transition", "task", task.id,
                    f"{old.value} -> {new_status.value}")
        self._emit("task.transitioned", task.id,
                   {"from": old.value, "to": new_status.value})
        return task

    # -- reads ----------------------------------------------------------
    def plan_summary(self, plan_id):
        plan = self.get_care_plan(plan_id)
        referrals = [r for r in self.store.referrals.values() if r.plan_id == plan_id]
        tasks = [t for t in self.store.tasks.values() if t.plan_id == plan_id]
        return {
            "plan": plan,
            "referrals": referrals,
            "tasks": tasks,
            "audit": self.store.audit_for(plan_id),
        }

    def process_outbox(self, handler):
        return self.dispatcher.dispatch_all(handler)
