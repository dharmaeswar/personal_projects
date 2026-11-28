"""Ingest tests."""

from datetime import datetime, timezone

from taskfeed.ingest import ingest, validate_raw

T0 = "2026-11-20T10:00:00+00:00"


def raw(**kw):
    base = dict(
        source="approvals",
        external_id="a1",
        title="Approve invoice",
        kind="approval",
        priority=3,
        created_at=T0,
    )
    base.update(kw)
    return base


def test_valid_batch_ingests():
    r = ingest([raw(), raw(external_id="a2", title="Second")])
    assert len(r.tasks) == 2 and not r.quarantined and r.duplicates_dropped == 0


def test_missing_field_quarantined():
    bad = raw()
    del bad["title"]
    r = ingest([bad])
    assert len(r.tasks) == 0 and len(r.quarantined) == 1
    assert "title" in r.quarantined[0].reason


def test_bad_kind_and_priority_quarantined():
    r = ingest([raw(kind="nope"), raw(external_id="x", priority=9)])
    assert len(r.tasks) == 0 and len(r.quarantined) == 2


def test_bad_dates_quarantined():
    r = ingest([raw(created_at="not-a-date"), raw(external_id="y", due_at="tomorrow")])
    assert len(r.quarantined) == 2


def test_duplicate_keeps_newest():
    old = raw(updated_at="2026-11-20T10:00:00+00:00", title="old")
    new = raw(updated_at="2026-11-21T10:00:00+00:00", title="new")
    r = ingest([old, new])
    assert len(r.tasks) == 1 and r.duplicates_dropped == 1
    assert r.tasks[0].title == "new"


def test_duplicate_keeps_first_on_tie():
    r = ingest([raw(title="first"), raw(title="second")])
    assert len(r.tasks) == 1 and r.tasks[0].title == "first"


def test_validate_raw_ok_and_not_object():
    assert validate_raw(raw()) is None
    assert validate_raw(["not", "a", "dict"]) is not None


def test_iso_z_suffix_parsed():
    r = ingest([raw(created_at="2026-11-20T10:00:00Z")])
    assert r.tasks[0].created_at == datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
