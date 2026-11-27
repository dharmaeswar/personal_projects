"""Tests for the Kafka-style event log (events.py)."""

import pytest

from vehicle_platform.events import EventError, EventLog, partition_for


def test_partition_is_deterministic():
    assert partition_for("ORD-1", 3) == partition_for("ORD-1", 3)
    assert 0 <= partition_for("ORD-1", 3) < 3


def test_publish_assigns_offsets_in_order():
    log = EventLog({"order-events": 3})
    first = log.publish("order-events", "ORD-1", {"type": "ORDER_CREATED"})
    second = log.publish("order-events", "ORD-1", {"type": "ORDER_ADVANCED"})
    assert first["partition"] == second["partition"]
    assert first["offset"] + 1 == second["offset"]


def test_read_key_returns_only_that_key():
    log = EventLog({"order-events": 3})
    log.publish("order-events", "ORD-1", {"type": "A"})
    log.publish("order-events", "ORD-2", {"type": "B"})
    log.publish("order-events", "ORD-1", {"type": "C"})
    records = log.read_key("order-events", "ORD-1")
    assert [r["payload"]["type"] for r in records] == ["A", "C"]


def test_read_from_offset():
    log = EventLog({"order-events": 1})
    for i in range(3):
        log.publish("order-events", "K", {"type": f"E{i}"})
    assert [r["payload"]["type"] for r in log.read("order-events", 0, 1)] == ["E1", "E2"]


def test_unknown_topic_rejected():
    log = EventLog()
    with pytest.raises(EventError):
        log.publish("no-such-topic", "K", {"type": "X"})


def test_event_without_type_goes_to_dlq():
    log = EventLog()
    with pytest.raises(EventError):
        log.publish("order-events", "ORD-9", {"status": "RESERVED"})
    assert len(log.dlq) == 1
    assert log.dlq[0]["key"] == "ORD-9"
    assert log.dlq[0]["reason"] == "payload missing event type"


def test_consumer_group_commit_and_lag():
    log = EventLog({"order-events": 1})
    log.publish("order-events", "K", {"type": "E0"})
    log.publish("order-events", "K", {"type": "E1"})
    assert log.lag("billing", "order-events", 0) == 2  # offsets 0..1, none committed
    log.commit("billing", "order-events", 0, 1)
    assert log.committed("billing", "order-events", 0) == 1
    assert log.lag("billing", "order-events", 0) == 0
    log.publish("order-events", "K", {"type": "E2"})
    assert log.lag("billing", "order-events", 0) == 1


def test_json_dump_round_trips():
    import json

    log = EventLog({"order-events": 1})
    log.publish("order-events", "K", {"type": "E0"})
    parsed = json.loads(log.to_json())
    assert parsed["records"]["order-events"][0][0]["payload"]["type"] == "E0"
