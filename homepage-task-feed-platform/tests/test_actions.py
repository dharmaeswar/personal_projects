"""Actions tests."""

from datetime import datetime, timedelta, timezone

import pytest

from taskfeed.actions import ActionError, ActionLog, detail_view
from taskfeed.models import Task

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def make(**kw):
    base = dict(
        source="approvals",
        external_id="a1",
        title="Approve invoice",
        kind="approval",
        priority=4,
        created_at=NOW - timedelta(days=1),
        payload={"requester": "Ana", "amount": "$1,200", "vendor": "Acme", "policy_checks": "pass"},
    )
    base.update(kw)
    return Task(**base)


def test_approve_moves_open_to_actioned():
    log, t = ActionLog(), make()
    r = log.apply(t, "approve", idempotency_key="k1", now=NOW)
    assert r["state"] == "actioned" and t.state == "actioned" and not r["replayed"]


def test_replay_returns_original_without_double_apply():
    log, t = ActionLog(), make()
    log.apply(t, "approve", idempotency_key="k1", now=NOW)
    r = log.apply(t, "approve", idempotency_key="k1", now=NOW)
    assert r["replayed"] and r["state"] == "actioned"


def test_terminal_state_rejects_new_actions():
    log, t = ActionLog(), make()
    log.apply(t, "dismiss", idempotency_key="k1", now=NOW)
    with pytest.raises(ActionError, match="cannot 'approve' a dismissed task"):
        log.apply(t, "approve", idempotency_key="k2", now=NOW)


def test_wrong_kind_action_rejected():
    log, t = ActionLog(), make(kind="receipt")
    with pytest.raises(ActionError, match="not valid for kind"):
        log.apply(t, "approve", idempotency_key="k1", now=NOW)


def test_unknown_action_rejected():
    log, t = ActionLog(), make()
    with pytest.raises(ActionError, match="unknown action"):
        log.apply(t, "teleport", idempotency_key="k1", now=NOW)


def test_snooze_sets_expiry_and_wakes():
    log, t = ActionLog(), make()
    log.apply(t, "snooze", idempotency_key="k1", now=NOW, snooze_days=2)
    assert t.state == "snoozed" and t.snoozed_until == NOW + timedelta(days=2)
    assert log.wake_snoozed([t], NOW + timedelta(days=1)) == 0
    assert log.wake_snoozed([t], NOW + timedelta(days=3)) == 1
    assert t.state == "open" and t.snoozed_until is None


def test_open_detail_never_changes_state():
    log, t = ActionLog(), make()
    r = log.apply(t, "open_detail", idempotency_key="k1", now=NOW)
    assert r["state"] == "open" and t.state == "open"


def test_detail_view_shape():
    v = detail_view(make(due_at=NOW + timedelta(days=2)))
    assert v.task_key == ("approvals", "a1")
    assert v.fields[0] == ("Requester", "Ana")
    assert ("Priority", "4") in v.fields
    assert "approve" in v.actions and "dismiss" in v.actions
    assert v.source == "approvals"


def test_detail_view_missing_payload_renders_dash():
    v = detail_view(make(payload={}))
    assert ("Amount", "—") in v.fields
