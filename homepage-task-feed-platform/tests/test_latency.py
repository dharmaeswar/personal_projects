"""Latency and degradation tests."""

from datetime import datetime, timedelta, timezone

from taskfeed.latency import LatencyTracker, SourceCache, fetch_with_budget
from taskfeed.models import Task

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def task():
    return Task(source="receipts", external_id="r1", title="Match receipt",
                kind="receipt", priority=2, created_at=NOW - timedelta(days=1))


def test_fast_source_ok_and_cached():
    cache, tracker = SourceCache(), LatencyTracker()
    res = fetch_with_budget("receipts", lambda: ([task()], 120.0), 250.0, cache, tracker)
    assert res.status == "ok" and len(res.tasks) == 1 and cache.has("receipts")
    assert tracker.p50("receipts") == 120.0


def test_slow_source_degrades_to_stale_cache():
    cache, tracker = SourceCache(), LatencyTracker()
    cache.store("receipts", [task()])
    res = fetch_with_budget("receipts", lambda: ([task()], 900.0), 250.0, cache, tracker)
    assert res.status == "degraded"
    assert len(res.tasks) == 1 and res.tasks[0].stale
    assert "over the 250ms budget" in res.notice


def test_slow_source_no_cache_degrades_empty():
    res = fetch_with_budget("receipts", lambda: ([task()], 900.0), 250.0,
                            SourceCache(), LatencyTracker())
    assert res.status == "degraded" and res.tasks == []


def test_failing_source_degrades_to_cache():
    cache, tracker = SourceCache(), LatencyTracker()
    cache.store("receipts", [task()])
    res = fetch_with_budget("receipts", lambda: (_ for _ in ()).throw(RuntimeError("down")),
                            250.0, cache, tracker)
    assert res.status == "degraded" and res.tasks[0].stale


def test_failing_source_no_cache_fails_cleanly():
    res = fetch_with_budget("receipts", lambda: (_ for _ in ()).throw(RuntimeError("down")),
                            250.0, SourceCache(), LatencyTracker())
    assert res.status == "failed" and res.tasks == [] and "failed" in res.notice


def test_p95_tracks_samples():
    tracker = LatencyTracker()
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        tracker.record("s", float(ms))
    assert tracker.p50("s") == 55.0
    assert 95.0 <= tracker.p95("s") <= 100.0
    assert tracker.p95("missing") is None
