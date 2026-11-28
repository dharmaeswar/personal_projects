"""Feed builder tests."""

from datetime import datetime, timedelta, timezone

from taskfeed.feed import FeedBuilder
from taskfeed.models import Task

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def task(source, ext, priority, days_old=1, due_in=None, relevance=0.5):
    return Task(source=source, external_id=ext, title=f"{source} {ext}",
                kind="approval", priority=priority,
                created_at=NOW - timedelta(days=days_old),
                due_at=NOW + timedelta(days=due_in) if due_in is not None else None,
                relevance=relevance)


def fetcher(tasks, latency=50.0):
    return lambda: (list(tasks), latency)


def test_build_ranks_and_reports_sources():
    b = FeedBuilder(budget_ms=250.0)
    feed = b.build({
        "approvals": fetcher([task("approvals", "a1", 5)]),
        "receipts": fetcher([task("receipts", "r1", 2)]),
    }, user="u1", now=NOW)
    assert [t.key for t in feed.tasks] == [("approvals", "a1"), ("receipts", "r1")]
    assert feed.scores[("approvals", "a1")] > feed.scores[("receipts", "r1")]
    assert all(s.status == "ok" for s in feed.sources)
    assert feed.stale_count == 0 and not feed.notices


def test_slow_source_degrades_but_feed_still_builds():
    b = FeedBuilder(budget_ms=250.0)
    b.cache.store("receipts", [task("receipts", "r1", 2)])
    feed = b.build({
        "approvals": fetcher([task("approvals", "a1", 5)]),
        "receipts": fetcher([task("receipts", "r1", 2)], latency=900.0),
    }, user="u1", now=NOW)
    assert len(feed.tasks) == 2
    assert feed.stale_count == 1
    assert len(feed.notices) == 1
    assert any(s.status == "degraded" for s in feed.sources)


def test_failed_source_with_no_cache_contributes_nothing():
    b = FeedBuilder()
    feed = b.build({
        "approvals": fetcher([task("approvals", "a1", 5)]),
        "receipts": lambda: (_ for _ in ()).throw(RuntimeError("down")),
    }, user="u1", now=NOW)
    assert [t.key for t in feed.tasks] == [("approvals", "a1")]
    assert any(s.status == "failed" for s in feed.sources)


def test_duplicate_task_across_sources_deduped():
    b = FeedBuilder()
    same = task("approvals", "a1", 4)
    feed = b.build({"approvals": fetcher([same]), "mirror": fetcher([same])},
                   user="u1", now=NOW)
    assert len(feed.tasks) == 1


def test_limit_applies():
    b = FeedBuilder()
    many = [task("approvals", f"a{i}", 3) for i in range(10)]
    feed = b.build({"approvals": fetcher(many)}, user="u1", now=NOW, limit=3)
    assert len(feed.tasks) == 3


def test_top_returns_first_n():
    b = FeedBuilder()
    feed = b.build({"approvals": fetcher([task("approvals", f"a{i}", 5 - i) for i in range(4)])},
                   user="u1", now=NOW)
    assert len(feed.top(2)) == 2
