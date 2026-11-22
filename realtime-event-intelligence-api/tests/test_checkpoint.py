"""Tests for schema validation, the dead-letter queue and checkpointing."""

from event_intel.checkpoint import (
    CheckpointStore,
    DeadLetterQueue,
    validate_signal,
)
from event_intel.pipeline import run_consumer
from event_intel.store import EventStore
from event_intel.stream import StreamTopic
from event_intel.windowing import TumblingWindows


def _signal(**overrides):
    base = {
        "source_id": "wire-1",
        "event_type": "outage",
        "text": "power outage downtown",
        "reliability": 0.9,
        "keyword_severity": 0.8,
        "corroborations": 2,
        "age_seconds": 60.0,
    }
    base.update(overrides)
    return base


def test_valid_signal_has_no_problems():
    assert validate_signal(_signal()) == []


def test_missing_required_field_flagged():
    signal = _signal()
    del signal["text"]
    problems = validate_signal(signal)
    assert any("text" in p for p in problems)


def test_non_object_signal_flagged():
    assert validate_signal("not a dict") == ["signal is not an object"]


def test_out_of_range_reliability_flagged():
    problems = validate_signal(_signal(reliability=1.5))
    assert any("reliability" in p for p in problems)


def test_negative_age_flagged():
    problems = validate_signal(_signal(age_seconds=-5))
    assert any("age_seconds" in p for p in problems)


def test_malformed_record_goes_to_dead_letter_queue():
    topic = StreamTopic("t", partitions=1)
    topic.publish("k", {"source_id": "", "event_type": "outage"})
    topic.publish("k", _signal())
    dlq = DeadLetterQueue()
    result = run_consumer(topic, EventStore(), "g", dead_letter=dlq)
    assert result["invalid"] == 1
    assert result["processed"] == 1
    assert len(dlq) == 1
    assert dlq.entries()[0]["problems"]


def test_redelivered_record_is_skipped_exactly_once():
    topic = StreamTopic("t", partitions=1)
    topic.publish("k", _signal())
    checkpoint = CheckpointStore()
    store = EventStore()
    first = run_consumer(topic, store, "g", checkpoint=checkpoint)
    assert first["processed"] == 1
    # Simulate a restart replay: same record re-polled for a fresh group.
    second = run_consumer(topic, store, "g2", checkpoint=checkpoint)
    assert second["redelivered_skipped"] == 1
    assert second["processed"] == 0


def test_checkpoint_snapshot_restores_offsets():
    checkpoint = CheckpointStore()
    checkpoint.mark_processed(0, 4)
    checkpoint.mark_processed(1, 2)
    snapshot = checkpoint.snapshot()
    assert snapshot["offsets"] == {0: 5, 1: 3}
    fresh = CheckpointStore()
    fresh.restore(snapshot)
    assert fresh.offsets == {0: 5, 1: 3}
    assert not fresh.already_processed(0, 0)  # seen-set is per-run, offsets carry the resume point


def test_windows_receive_scored_events_from_pipeline():
    topic = StreamTopic("t", partitions=1)
    topic.publish("k", _signal(event_time=5.0))
    topic.publish("k", _signal(text="second event", event_time=65.0))
    windows = TumblingWindows(window_seconds=60.0)
    run_consumer(topic, EventStore(), "g", windows=windows)
    closed = windows.close_all()
    assert [w.window_start for w in closed] == [0.0, 60.0]
    assert sum(w.events for w in closed) == 2
