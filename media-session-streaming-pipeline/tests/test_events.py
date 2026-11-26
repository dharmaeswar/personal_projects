from datetime import datetime, timezone

from session_stream.events import EVENT_TYPES, generate_sessions, Topic


def _base_event(**over):
    ev = {
        "event_id": "e1", "session_id": "s1", "user_id": "u1",
        "title_id": "title-001", "device": "tv", "region": "us-west",
        "app": "video", "event_type": "heartbeat",
        "event_ts": datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
        "playhead_seconds": 30.0, "bitrate_kbps": 4500,
    }
    ev.update(over)
    return ev


def test_generate_is_deterministic():
    a = generate_sessions(10, seed=7)
    b = generate_sessions(10, seed=7)
    assert a == b


def test_generate_different_seeds_differ():
    assert generate_sessions(10, seed=7) != generate_sessions(10, seed=8)


def test_generate_session_structure():
    events = generate_sessions(5, seed=42)
    assert events
    types = {e["event_type"] for e in events}
    assert "session_start" in types and "session_end" in types
    assert types <= set(EVENT_TYPES)
    for e in events:
        assert e["playhead_seconds"] >= 0
        assert e["bitrate_kbps"] >= 0
    # events are time-ordered
    ts = [e["event_ts"] for e in events]
    assert ts == sorted(ts)


def test_generate_session_ids_grouped():
    events = generate_sessions(5, seed=42)
    sessions = {e["session_id"] for e in events}
    assert len(sessions) == 5
    for sid in sessions:
        seq = [e for e in events if e["session_id"] == sid]
        assert seq[0]["event_type"] == "session_start"
        assert seq[-1]["event_type"] == "session_end"
        playheads = [e["playhead_seconds"] for e in seq]
        assert playheads[-1] == max(playheads)


def test_topic_partitions_by_key():
    topic = Topic("sessions", partitions=4)
    p1, o1 = topic.produce(_base_event(), key="s1")
    p2, o2 = topic.produce(_base_event(event_id="e2"), key="s1")
    assert p1 == p2 and o1 == 0 and o2 == 1
    assert topic.size() == 2


def test_topic_poll_commits_offsets():
    topic = Topic("sessions", partitions=2)
    for i in range(5):
        topic.produce(_base_event(event_id=f"e{i}"), key=f"s{i}")
    first = topic.poll("g1", max_records=10)
    assert len(first) == 5
    second = topic.poll("g1", max_records=10)
    assert second == []
    other_group = topic.poll("g2", max_records=10)
    assert len(other_group) == 5
    assert topic.committed_offsets("g1")
