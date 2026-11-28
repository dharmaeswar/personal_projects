"""Task model tests."""

from datetime import datetime, timedelta, timezone

import pytest

from taskfeed.models import KIND_ACTIONS, STANDARD_ACTIONS, TASK_KINDS, Task, utcnow


def make_task(**kw):
    base = dict(
        source="approvals",
        external_id="a1",
        title="Approve $1,200 vendor invoice",
        kind="approval",
        priority=3,
        created_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )
    base.update(kw)
    return Task(**base)


def test_valid_task_defaults():
    t = make_task()
    assert t.state == "open"
    assert t.key == ("approvals", "a1")
    assert t.updated_at == t.created_at
    assert not t.stale
    assert set(t.allowed_actions()) == set(KIND_ACTIONS["approval"])


def test_unknown_kind_rejected():
    with pytest.raises(ValueError, match="unknown task kind"):
        make_task(kind="mystery")


@pytest.mark.parametrize("p", [0, 6, -1])
def test_priority_bounds(p):
    with pytest.raises(ValueError, match="priority"):
        make_task(priority=p)


@pytest.mark.parametrize("r", [-0.1, 1.1])
def test_relevance_bounds(r):
    with pytest.raises(ValueError, match="relevance"):
        make_task(relevance=r)


def test_bad_state_rejected():
    with pytest.raises(ValueError, match="unknown task state"):
        make_task(state="archived")


def test_overdue_only_when_open_and_past_due():
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    assert make_task(due_at=now - timedelta(days=1)).is_overdue(now)
    assert not make_task(due_at=now + timedelta(days=1)).is_overdue(now)
    assert not make_task(due_at=None).is_overdue(now)
    assert not make_task(due_at=now - timedelta(days=1), state="actioned").is_overdue(now)


def test_every_kind_has_dismiss_snooze_detail():
    for kind in TASK_KINDS:
        assert "dismiss" in KIND_ACTIONS[kind]
        assert "snooze" in KIND_ACTIONS[kind]
        assert "open_detail" in KIND_ACTIONS[kind]
    assert "approve" in STANDARD_ACTIONS and "complete" in STANDARD_ACTIONS


def test_utcnow_is_utc():
    assert utcnow().tzinfo is timezone.utc
