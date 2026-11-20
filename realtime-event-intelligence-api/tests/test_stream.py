import pytest

from event_intel.stream import StreamTopic


def test_publish_assigns_partition_and_offset():
    topic = StreamTopic("t", partitions=3)
    r1 = topic.publish("key-a", {"v": 1})
    r2 = topic.publish("key-a", {"v": 2})
    assert r1.partition == r2.partition
    assert r1.offset == 0
    assert r2.offset == 1


def test_poll_returns_in_offset_order_and_commit_advances():
    topic = StreamTopic("t", partitions=2)
    for i in range(5):
        topic.publish(f"k{i}", {"i": i})
    batch = topic.poll("g1", max_records=10)
    assert len(batch) == 5
    # offsets increase within each partition (partition-major order)
    for partition in range(2):
        offsets = [r.offset for r in batch if r.partition == partition]
        assert offsets == sorted(offsets)
    topic.commit("g1", batch)
    assert topic.poll("g1") == []
    assert topic.lag("g1") == 0


def test_consumer_groups_track_offsets_independently():
    topic = StreamTopic("t", partitions=2)
    topic.publish("k", {"v": 1})
    topic.publish("k", {"v": 2})
    assert len(topic.poll("g1")) == 2
    assert len(topic.poll("g2")) == 2
    topic.commit("g1", topic.poll("g1"))
    assert topic.poll("g1") == []
    assert len(topic.poll("g2")) == 2


def test_lag_counts_unread_records():
    topic = StreamTopic("t", partitions=2)
    assert topic.lag("g1") == 0
    topic.publish("a", {})
    topic.publish("b", {})
    topic.publish("c", {})
    assert topic.lag("g1") == 3
    batch = topic.poll("g1", max_records=2)
    topic.commit("g1", batch)
    assert topic.lag("g1") == 1


def test_max_records_limits_batch():
    topic = StreamTopic("t", partitions=1)
    for i in range(6):
        topic.publish("k", {"i": i})
    assert len(topic.poll("g1", max_records=4)) == 4


def test_invalid_partitions_rejected():
    with pytest.raises(ValueError):
        StreamTopic("t", partitions=0)
