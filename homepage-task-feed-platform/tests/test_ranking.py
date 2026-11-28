"""Ranking tests."""

from datetime import datetime, timedelta, timezone

from taskfeed.models import Task
from taskfeed.ranking import freshness_factor, rank, score, urgency_bonus

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def make(**kw):
    base = dict(
        source="approvals",
        external_id="a1",
        title="t",
        kind="approval",
        priority=3,
        created_at=NOW - timedelta(days=1),
    )
    base.update(kw)
    return Task(**base)


def test_priority_drives_score():
    assert score(make(priority=5), NOW) > score(make(priority=1), NOW)


def test_overdue_beats_due_today_beats_this_week():
    o = urgency_bonus(make(due_at=NOW - timedelta(days=1)), NOW)
    t = urgency_bonus(make(due_at=NOW + timedelta(hours=2)), NOW)
    w = urgency_bonus(make(due_at=NOW + timedelta(days=3)), NOW)
    n = urgency_bonus(make(due_at=NOW + timedelta(days=30)), NOW)
    assert o > t > w > n == 0.0


def test_no_due_date_no_bonus():
    assert urgency_bonus(make(due_at=None), NOW) == 0.0


def test_freshness_decays_but_floors():
    fresh = freshness_factor(make(created_at=NOW), NOW)
    old = freshness_factor(make(created_at=NOW - timedelta(days=365)), NOW)
    assert fresh == 1.0
    assert 0.5 <= old < 0.6


def test_rank_orders_by_score_and_breaks_ties_deterministically():
    low = make(external_id="low", priority=1)
    high = make(external_id="high", priority=5)
    mid = make(external_id="mid", priority=3)
    assert [t.external_id for t in rank([low, mid, high], NOW)] == ["high", "mid", "low"]
    a = make(external_id="a", created_at=NOW - timedelta(days=2))
    b = make(external_id="b", created_at=NOW - timedelta(days=2))
    assert [t.external_id for t in rank([b, a], NOW)] == ["a", "b"]


def test_relevance_breaks_priority_tie():
    a = make(external_id="a", priority=3, relevance=0.9)
    b = make(external_id="b", priority=3, relevance=0.1)
    assert rank([b, a], NOW)[0].external_id == "a"
