"""Tests for the care-coordination service: state machines, idempotency, audit."""

import pytest

from care_coord.models import PlanStatus, ReferralStatus, TaskStatus
from care_coord.service import (
    CareCoordinationService, InvalidTransitionError, NotFoundError, ValidationError,
)


@pytest.fixture
def svc():
    return CareCoordinationService()


@pytest.fixture
def active_plan(svc):
    plan = svc.create_care_plan("PAT-0001", "Follow-up", ["goal A"])
    svc.transition_plan(plan.id, "active")
    return plan


def test_create_plan_starts_draft(svc):
    plan = svc.create_care_plan("PAT-0001", "Follow-up")
    assert plan.status is PlanStatus.DRAFT
    assert plan.patient_ref == "PAT-0001"
    assert plan.goals == []


def test_create_plan_requires_title(svc):
    with pytest.raises(ValidationError):
        svc.create_care_plan("PAT-0001", "")


def test_create_plan_requires_patient_ref(svc):
    with pytest.raises(ValidationError):
        svc.create_care_plan("", "Follow-up")


def test_plan_draft_to_active(svc):
    plan = svc.create_care_plan("PAT-0001", "Follow-up")
    svc.transition_plan(plan.id, "active")
    assert svc.get_care_plan(plan.id).status is PlanStatus.ACTIVE


def test_plan_cannot_skip_draft_to_completed(svc):
    plan = svc.create_care_plan("PAT-0001", "Follow-up")
    with pytest.raises(InvalidTransitionError):
        svc.transition_plan(plan.id, "completed")


def test_plan_cannot_complete_with_open_referral(svc, active_plan):
    svc.add_referral(active_plan.id, "cardiology")
    with pytest.raises(InvalidTransitionError):
        svc.transition_plan(active_plan.id, "completed")


def test_plan_cannot_complete_with_open_task(svc, active_plan):
    svc.create_task(active_plan.id, "Call patient")
    with pytest.raises(InvalidTransitionError):
        svc.transition_plan(active_plan.id, "completed")


def test_plan_completes_when_everything_terminal(svc, active_plan):
    ref = svc.add_referral(active_plan.id, "cardiology")
    svc.transition_referral(ref.id, "accepted")
    svc.transition_referral(ref.id, "scheduled")
    svc.transition_referral(ref.id, "completed")
    task = svc.create_task(active_plan.id, "Call patient")
    svc.transition_task(task.id, "in_progress")
    svc.transition_task(task.id, "done")
    svc.transition_plan(active_plan.id, "completed")
    assert svc.get_care_plan(active_plan.id).status is PlanStatus.COMPLETED


def test_plan_on_hold_and_back(svc, active_plan):
    svc.transition_plan(active_plan.id, "on_hold")
    assert svc.get_care_plan(active_plan.id).status is PlanStatus.ON_HOLD
    svc.transition_plan(active_plan.id, "active")
    assert svc.get_care_plan(active_plan.id).status is PlanStatus.ACTIVE


def test_completed_plan_is_terminal(svc, active_plan):
    svc.transition_plan(active_plan.id, "completed")
    with pytest.raises(InvalidTransitionError):
        svc.transition_plan(active_plan.id, "active")


def test_get_unknown_plan_raises(svc):
    with pytest.raises(NotFoundError):
        svc.get_care_plan("nope")


def test_referral_happy_path(svc, active_plan):
    ref = svc.add_referral(active_plan.id, "cardiology", "follow-up")
    assert ref.status is ReferralStatus.REQUESTED
    svc.transition_referral(ref.id, "accepted")
    svc.transition_referral(ref.id, "scheduled")
    svc.transition_referral(ref.id, "completed")
    assert svc.store.referrals[ref.id].status is ReferralStatus.COMPLETED


def test_referral_cannot_skip_to_scheduled(svc, active_plan):
    ref = svc.add_referral(active_plan.id, "cardiology")
    with pytest.raises(InvalidTransitionError):
        svc.transition_referral(ref.id, "scheduled")


def test_referral_can_be_declined(svc, active_plan):
    ref = svc.add_referral(active_plan.id, "cardiology")
    svc.transition_referral(ref.id, "declined")
    assert svc.store.referrals[ref.id].status is ReferralStatus.DECLINED


def test_no_referral_on_completed_plan(svc, active_plan):
    svc.transition_plan(active_plan.id, "completed")
    with pytest.raises(InvalidTransitionError):
        svc.add_referral(active_plan.id, "cardiology")


def test_task_happy_path_with_block(svc, active_plan):
    task = svc.create_task(active_plan.id, "Call patient", assignee="team-1")
    assert task.status is TaskStatus.OPEN
    svc.transition_task(task.id, "in_progress")
    svc.transition_task(task.id, "blocked")
    svc.transition_task(task.id, "in_progress")
    svc.transition_task(task.id, "done")
    assert svc.store.tasks[task.id].status is TaskStatus.DONE


def test_task_cannot_go_from_done(svc, active_plan):
    task = svc.create_task(active_plan.id, "Call patient")
    svc.transition_task(task.id, "in_progress")
    svc.transition_task(task.id, "done")
    with pytest.raises(InvalidTransitionError):
        svc.transition_task(task.id, "in_progress")


def test_task_requires_title(svc, active_plan):
    with pytest.raises(ValidationError):
        svc.create_task(active_plan.id, "")


def test_audit_trail_records_every_mutation(svc, active_plan):
    ref = svc.add_referral(active_plan.id, "cardiology")
    svc.transition_referral(ref.id, "accepted")
    actions = [a.action for a in svc.store.audit]
    assert "care_plan.created" in actions
    assert "care_plan.transition" in actions
    assert "referral.requested" in actions
    assert "referral.transition" in actions
    assert len(svc.store.audit_for(active_plan.id)) >= 2


def test_create_plan_emits_outbox_event(svc):
    plan = svc.create_care_plan("PAT-0001", "Follow-up")
    pending = svc.store.pending_events()
    assert len(pending) == 1
    assert pending[0].event_type == "care_plan.created"
    assert pending[0].aggregate_id == plan.id


def test_idempotent_create_plan_same_request_key(svc):
    a = svc.create_care_plan("PAT-0001", "Follow-up", request_key="req-1")
    b = svc.create_care_plan("PAT-0001", "Follow-up", request_key="req-1")
    assert a.id == b.id
    assert len(svc.store.plans) == 1
    assert len(svc.store.pending_events()) == 1


def test_different_request_keys_create_two_plans(svc):
    svc.create_care_plan("PAT-0001", "Follow-up", request_key="req-1")
    svc.create_care_plan("PAT-0001", "Follow-up", request_key="req-2")
    assert len(svc.store.plans) == 2


def test_idempotent_referral_same_request_key(svc, active_plan):
    a = svc.add_referral(active_plan.id, "cardiology", request_key="ref-1")
    b = svc.add_referral(active_plan.id, "cardiology", request_key="ref-1")
    assert a.id == b.id
    assert len(svc.store.referrals) == 1


def test_plan_summary_bundles_children_and_audit(svc, active_plan):
    svc.add_referral(active_plan.id, "cardiology")
    svc.create_task(active_plan.id, "Call patient")
    summary = svc.plan_summary(active_plan.id)
    assert len(summary["referrals"]) == 1
    assert len(summary["tasks"]) == 1
    assert len(summary["audit"]) >= 2
