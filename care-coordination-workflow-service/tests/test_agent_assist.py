"""Tests for the agent-assist suggestion engine (human-in-the-loop).

All data is synthetic and de-identified (opaque PAT-#### references).
"""

from datetime import datetime, timedelta, timezone

import pytest

from care_coord.agent_assist import (
    AgentAssist,
    SuggestionDecidedError,
    SuggestionNotFoundError,
)
from care_coord.models import PlanStatus, TaskStatus
from care_coord.service import CareCoordinationService


def _service_with_plan():
    service = CareCoordinationService()
    plan = service.create_care_plan("PAT-0001", "Post-discharge follow-up",
                                    ["Schedule cardiology follow-up"])
    service.transition_plan(plan.id, "active")
    return service, plan


def _days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_follow_up_for_stale_referral():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    assist = AgentAssist(service)
    suggestions = assist.suggest_for_plan(plan.id)
    assert len(suggestions) == 1
    assert suggestions[0].kind == "follow_up_referral"
    assert "cardiology" in suggestions[0].summary
    assert suggestions[0].status == "proposed"


def test_no_follow_up_for_fresh_referral():
    service, plan = _service_with_plan()
    service.add_referral(plan.id, "cardiology", "follow-up")
    assist = AgentAssist(service)
    assert assist.suggest_for_plan(plan.id) == []


def test_escalate_blocked_task():
    service, plan = _service_with_plan()
    task = service.create_task(plan.id, "Call patient to confirm appointment")
    service.transition_task(task.id, "in_progress")
    service.transition_task(task.id, "blocked")
    assist = AgentAssist(service)
    suggestions = assist.suggest_for_plan(plan.id)
    assert [s.kind for s in suggestions] == ["escalate_blocked_task"]
    assert "Call patient" in suggestions[0].summary


def test_complete_plan_when_work_done():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    service.transition_referral(ref.id, "accepted")
    service.transition_referral(ref.id, "scheduled")
    task = service.create_task(plan.id, "Call patient")
    service.transition_task(task.id, "in_progress")
    service.transition_task(task.id, "done")
    service.transition_referral(ref.id, "completed")
    assist = AgentAssist(service)
    suggestions = assist.suggest_for_plan(plan.id)
    assert [s.kind for s in suggestions] == ["complete_plan"]


def test_no_complete_plan_while_work_open():
    service, plan = _service_with_plan()
    service.add_referral(plan.id, "cardiology", "follow-up")
    service.create_task(plan.id, "Call patient")
    assist = AgentAssist(service)
    assert assist.suggest_for_plan(plan.id) == []


def test_review_on_hold_plan_with_nothing_open():
    service, plan = _service_with_plan()
    service.transition_plan(plan.id, "on_hold")
    assist = AgentAssist(service)
    suggestions = assist.suggest_for_plan(plan.id)
    assert [s.kind for s in suggestions] == ["review_on_hold"]


def test_no_suggestions_for_draft_or_completed_plan():
    service = CareCoordinationService()
    draft = service.create_care_plan("PAT-0002", "Draft plan")
    assist = AgentAssist(service)
    assert assist.suggest_for_plan(draft.id) == []

    service2, plan = _service_with_plan()
    assist2 = AgentAssist(service2)
    ref = service2.add_referral(plan.id, "cardiology", "follow-up")
    service2.transition_referral(ref.id, "accepted")
    service2.transition_referral(ref.id, "scheduled")
    task = service2.create_task(plan.id, "Call patient")
    service2.transition_task(task.id, "in_progress")
    service2.transition_task(task.id, "done")
    service2.transition_referral(ref.id, "completed")
    service2.transition_plan(plan.id, "completed")
    assert assist2.suggest_for_plan(plan.id) == []


def test_suggest_twice_does_not_duplicate():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    assist = AgentAssist(service)
    first = assist.suggest_for_plan(plan.id)
    second = assist.suggest_for_plan(plan.id)
    assert len(first) == 1 and len(second) == 1
    assert first[0].id == second[0].id
    assert len(assist.list_suggestions(plan.id)) == 1


def test_approve_follow_up_creates_task_and_audits():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    assist = AgentAssist(service)
    suggestion = assist.suggest_for_plan(plan.id)[0]
    decided = assist.approve(suggestion.id, actor="operator-7")
    assert decided.status == "approved"
    assert decided.decided_by == "operator-7"
    tasks = [t for t in service.store.tasks.values() if t.plan_id == plan.id]
    assert any("Follow up on cardiology referral" in t.title for t in tasks)
    actions = [a.action for a in service.store.audit]
    assert "agent_suggestion.approved" in actions


def test_approve_complete_plan_closes_it():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    service.transition_referral(ref.id, "accepted")
    service.transition_referral(ref.id, "scheduled")
    task = service.create_task(plan.id, "Call patient")
    service.transition_task(task.id, "in_progress")
    service.transition_task(task.id, "done")
    service.transition_referral(ref.id, "completed")
    assist = AgentAssist(service)
    suggestion = assist.suggest_for_plan(plan.id)[0]
    assist.approve(suggestion.id, actor="operator-7")
    assert service.get_care_plan(plan.id).status is PlanStatus.COMPLETED


def test_reject_applies_nothing_and_audits():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    assist = AgentAssist(service)
    suggestion = assist.suggest_for_plan(plan.id)[0]
    decided = assist.reject(suggestion.id, actor="operator-7",
                            reason="family already contacted the clinic")
    assert decided.status == "rejected"
    assert decided.decision_reason == "family already contacted the clinic"
    assert service.store.tasks == {}
    actions = [a.action for a in service.store.audit]
    assert "agent_suggestion.rejected" in actions


def test_decide_twice_raises_and_unknown_id_raises():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    assist = AgentAssist(service)
    suggestion = assist.suggest_for_plan(plan.id)[0]
    assist.approve(suggestion.id)
    with pytest.raises(SuggestionDecidedError):
        assist.approve(suggestion.id)
    with pytest.raises(SuggestionDecidedError):
        assist.reject(suggestion.id)
    with pytest.raises(SuggestionNotFoundError):
        assist.approve("no-such-id")
    with pytest.raises(SuggestionNotFoundError):
        assist.reject("no-such-id")


def test_suggest_unknown_plan_raises():
    assist = AgentAssist(CareCoordinationService())
    with pytest.raises(KeyError):
        assist.suggest_for_plan("no-such-plan")


def test_list_suggestions_filters():
    service, plan = _service_with_plan()
    ref = service.add_referral(plan.id, "cardiology", "follow-up")
    ref.created_at = _days_ago(10)
    task = service.create_task(plan.id, "Call patient")
    service.transition_task(task.id, "in_progress")
    service.transition_task(task.id, "blocked")
    assist = AgentAssist(service)
    suggestions = assist.suggest_for_plan(plan.id)
    assert len(suggestions) == 2
    kinds = {s.kind for s in suggestions}
    assert kinds == {"follow_up_referral", "escalate_blocked_task"}
    assist.reject(suggestions[0].id, actor="operator-7")
    assert len(assist.list_suggestions(plan.id, status="proposed")) == 1
    assert len(assist.list_suggestions(plan.id, status="rejected")) == 1
    assert len(assist.list_suggestions()) == 2
