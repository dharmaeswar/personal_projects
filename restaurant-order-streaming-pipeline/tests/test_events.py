from datetime import datetime

from order_stream.events import KafkaTopic, OrderEvent, seed_events


def test_seed_is_deterministic():
    assert [e.order_id for e in seed_events()] == [e.order_id for e in seed_events()]


def test_seed_plants_duplicates_and_bad_rows():
    events = seed_events()
    ids = [e.order_id for e in events]
    assert len(ids) - len(set(ids)) == 5  # 3 re-delivered duplicates + 2 late copies
    assert any(e.quantity < 0 for e in events)
    assert any(e.menu_code == "M999" for e in events)


def test_topic_partitions_by_restaurant_and_tracks_offsets():
    topic = KafkaTopic("t", partitions=4)
    event = OrderEvent("ORD-1", "R1001", datetime(2026, 11, 20, 11, 0), "counter", "M001", 1, 5.99, 5.99)
    partition, offset = topic.produce(event)
    assert partition == topic.partition_for("R1001")
    assert offset == 0
    assert topic.lag("g1") == 1
    got = topic.poll("g1")
    assert got == [event]
    topic.commit("g1", got)
    assert topic.lag("g1") == 0


def test_same_restaurant_always_same_partition():
    topic = KafkaTopic("t", partitions=4)
    e1 = OrderEvent("ORD-1", "R1002", datetime(2026, 11, 20, 11, 0), "kiosk", "M002", 1, 6.49, 6.49)
    e2 = OrderEvent("ORD-2", "R1002", datetime(2026, 11, 20, 11, 1), "kiosk", "M002", 2, 6.49, 12.98)
    assert topic.produce(e1)[0] == topic.produce(e2)[0]
