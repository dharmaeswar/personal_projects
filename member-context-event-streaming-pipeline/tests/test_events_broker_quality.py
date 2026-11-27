"""Tests: event generation, broker semantics, contracts/quality."""

from datetime import datetime, timedelta, timezone

from member_context.broker import ConsumerGroup, InMemoryBroker
from member_context.contracts import CONTRACTS, check_quality
from member_context.events import generate_events

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def test_generate_is_seeded_and_deterministic():
    a = generate_events(n_members=5, events_per_member=10, seed=7)
    b = generate_events(n_members=5, events_per_member=10, seed=7)
    assert [(e.event_id, e.member_id, e.event_type) for e in a] == [
        (e.event_id, e.member_id, e.event_type) for e in b
    ]
    assert len(a) > 0


def test_generate_includes_duplicates_and_bad_rows():
    events = generate_events(n_members=40, events_per_member=25, seed=42)
    ids = [e.event_id for e in events]
    assert len(ids) > len(set(ids)), "expected producer re-deliveries"
    assert any(e.event_type == "mystery_event" for e in events)


def test_broker_partitions_by_member_key_and_offsets():
    broker = InMemoryBroker()
    topic = broker.create_topic("member-events", partitions=6)
    events = generate_events(n_members=5, events_per_member=10, seed=3)
    for e in events:
        topic.produce(e)
    assert topic.total_records() == len(events)
    for p in range(6):
        offsets = [r.offset for r in topic.logs[p]]
        assert offsets == list(range(len(offsets)))
    # Same member always lands in the same partition (key ordering).
    partitions = {topic.partition_for(e.member_id) for e in events if e.member_id == "member-0000"}
    assert len(partitions) == 1


def test_consumer_group_lag_and_commit():
    broker = InMemoryBroker()
    topic = broker.create_topic("member-events", partitions=2)
    events = generate_events(n_members=3, events_per_member=10, seed=5)
    for e in events:
        topic.produce(e)
    group = ConsumerGroup("g1")
    assert group.total_lag(topic) == len(events)
    for p in range(2):
        records = topic.fetch(p, 0, max_records=1000)
        if records:
            group.commit("member-events", p, records[-1].offset + 1)
    assert group.total_lag(topic) == 0


def test_contracts_cover_every_event_type():
    for event_type in (
        "web_page_view", "app_open", "search", "plan_browse", "care_search",
        "agent_message", "outbound_click", "benefit_view", "claim_status_check",
    ):
        assert event_type in CONTRACTS
        assert CONTRACTS[event_type].version == "1.0"


def test_quality_dedupes_and_quarantines():
    events = generate_events(n_members=40, events_per_member=25, seed=42)
    result = check_quality(events, now=NOW)
    assert result.duplicates_dropped > 0, "re-deliveries should be dropped"
    assert len(result.quarantined) > 0, "bad rows should be quarantined"
    assert result.total_seen == len(events)
    valid_ids = {e.event_id for e in result.valid}
    assert len(valid_ids) == len(result.valid), "valid set must be deduped"
    reasons = " ".join(q.reason for q in result.quarantined)
    assert "missing required field" in reasons
    assert "no contract" in reasons
    assert "in the future" in reasons
    assert "negative" in reasons


def test_quality_keeps_valid_events_intact():
    events = generate_events(n_members=5, events_per_member=10, seed=11)
    result = check_quality(events, now=NOW)
    assert len(result.valid) > 0
    for e in result.valid:
        assert e.event_type in CONTRACTS
