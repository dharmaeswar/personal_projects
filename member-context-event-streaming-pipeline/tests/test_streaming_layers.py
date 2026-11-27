"""Tests: stream processing, context layers, lineage/SLOs, full pipeline."""

from datetime import datetime, timedelta, timezone

from member_context.context_layers import (
    action_journey_catalogue,
    build_llm_documents,
    build_snapshot_rows,
)
from member_context.contracts import check_quality
from member_context.events import MemberEvent, generate_events
from member_context.lineage import evaluate_slo, fingerprint
from member_context.orchestration import run_pipeline
from member_context.streaming import build_member_context, build_sessions, windowed_counts

AS_OF = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _valid_events(seed=42):
    events = generate_events(n_members=10, events_per_member=20, seed=seed)
    return check_quality(events, now=NOW).valid


def _event(member, etype, occurred, payload=None):
    return MemberEvent(
        event_id=f"evt-{member}-{etype}-{occurred.isoformat()}",
        member_id=member,
        event_type=etype,
        occurred_at=occurred,
        ingested_at=occurred + timedelta(seconds=10),
        channel="web",
        payload=payload or {"session_id": "s1", "page": "/home"},
    )


def test_sessions_split_on_30_minute_gap():
    base = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
    events = [
        _event("m1", "web_page_view", base),
        _event("m1", "search", base + timedelta(minutes=10),
               {"session_id": "s1", "query": "find doctor"}),
        _event("m1", "app_open", base + timedelta(hours=2), {"session_id": "s2"}),
    ]
    sessions = build_sessions(events)
    assert len(sessions) == 2
    assert sessions[0].event_count == 2
    assert sessions[1].event_count == 1


def test_member_context_is_point_in_time_correct():
    base = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
    as_of = base + timedelta(hours=1)
    events = [
        _event("m1", "web_page_view", base),
        # This event happens AFTER as_of: it must never appear in the context.
        _event("m1", "care_search", as_of + timedelta(hours=1),
               {"session_id": "s1", "specialty": "dermatology"}),
    ]
    ctx = build_member_context(events, "m1", as_of)
    assert ctx.events_7d == 1
    assert ctx.last_event_type == "web_page_view"
    assert ctx.event_counts_7d.get("care_search", 0) == 0


def test_member_context_empty_member():
    ctx = build_member_context([], "nobody", AS_OF)
    assert ctx.events_7d == 0
    assert ctx.sessions_7d == 0
    assert ctx.last_event_at is None
    assert ctx.days_since_last_event is None


def test_windowed_counts_respect_window():
    events = _valid_events()
    counts = windowed_counts(events, AS_OF)
    assert counts, "expected some members in the 7-day window"
    for member_counts in counts.values():
        assert sum(member_counts.values()) > 0


def test_snapshot_rows_cover_all_members():
    events = _valid_events()
    member_ids = sorted({e.member_id for e in events})
    rows = build_snapshot_rows(events, member_ids, AS_OF)
    assert len(rows) == len(member_ids)
    for row in rows:
        d = row.to_dict()
        assert d["events_7d"] >= 0
        assert d["as_of"] == AS_OF.isoformat()


def test_llm_documents_have_journey_and_actions():
    events = _valid_events()
    member_ids = sorted({e.member_id for e in events})
    docs = build_llm_documents(events, member_ids, AS_OF)
    assert len(docs) == len(member_ids)
    for doc in docs:
        d = doc.to_dict()
        assert d["summary"].startswith("Member ")
        assert isinstance(d["recent_journey"], list)
        assert len(d["suggested_actions"]) >= 1
        assert all("action_id" in a for a in d["suggested_actions"])


def test_action_catalogue_is_stable():
    catalogue = action_journey_catalogue()
    assert len(catalogue) == 8
    assert {a["journey"] for a in catalogue} >= {
        "find_care", "understand_plan", "track_claim", "get_help", "stay_healthy",
    }


def test_fingerprint_is_deterministic_and_sensitive():
    rows = [{"a": 1}, {"b": 2}]
    assert fingerprint(rows) == fingerprint(rows)
    assert fingerprint(rows) != fingerprint([{"a": 1}, {"b": 3}])


def test_slo_evaluation():
    slo = evaluate_slo("run-x", valid_rows=990, quarantined_rows=10,
                       freshness_p95_minutes=5.0)
    assert slo.completeness_ratio == 0.99
    assert slo.freshness_met is True
    assert slo.completeness_met is True
    assert slo.all_met is True
    slow = evaluate_slo("run-y", valid_rows=100, quarantined_rows=0,
                        freshness_p95_minutes=60.0)
    assert slow.freshness_met is False
    assert slow.all_met is False


def test_full_pipeline_run():
    manifest, layers = run_pipeline(n_members=40, events_per_member=25, seed=42)
    assert manifest.produced == manifest.consumed
    assert manifest.valid > 0
    assert manifest.quarantined > 0
    assert manifest.duplicates_dropped > 0
    assert manifest.valid + manifest.quarantined + manifest.duplicates_dropped == manifest.produced
    assert manifest.sessions > 0
    assert manifest.snapshot_rows == 40
    assert manifest.llm_documents == 40
    assert len(manifest.lineage) == 3
    assert manifest.slo["completeness_ratio"] >= 0.9
    assert manifest.slo["all_met"] is True
    assert len(layers["quarantined"]) == manifest.quarantined
    assert layers["snapshots"][0]["member_id"].startswith("member-")
