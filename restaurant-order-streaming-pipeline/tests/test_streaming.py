from datetime import datetime, timedelta

from order_stream.events import OrderEvent
from order_stream.streaming import run_micro_batch, split_batches, window_start


def _event(order_id, at, restaurant="R1001"):
    return OrderEvent(order_id, restaurant, at, "counter", "M001", 1, 5.99, 5.99)


def test_window_start_floors_to_15_minutes():
    assert window_start(datetime(2026, 11, 20, 11, 23, 40)) == datetime(2026, 11, 20, 11, 15)
    assert window_start(datetime(2026, 11, 20, 11, 0, 5)) == datetime(2026, 11, 20, 11, 0)


def test_split_batches_flags_events_behind_watermark_as_late():
    base = datetime(2026, 11, 20, 11, 0)
    first = [_event(f"ORD-{i}", base + timedelta(minutes=i)) for i in range(40)]
    late = _event("ORD-LATE", base - timedelta(hours=2))
    batches = split_batches(first + [late], batch_size=40)
    assert len(batches) == 2
    assert batches[1].late == [late]
    assert late not in batches[1].events


def test_micro_batch_aggregates_revenue_per_window_and_restaurant():
    base = datetime(2026, 11, 20, 11, 0)
    from order_stream.streaming import MicroBatch

    batch = MicroBatch(0, base, [
        _event("ORD-1", base + timedelta(minutes=2)),
        _event("ORD-2", base + timedelta(minutes=5)),
        _event("ORD-3", base + timedelta(minutes=20), restaurant="R1002"),
    ])
    _, agg = run_micro_batch(batch)
    assert len(agg) == 2
    row = agg[(agg["restaurant_id"] == "R1001")].iloc[0]
    assert row["orders"] == 2 and abs(row["revenue"] - 11.98) < 0.01


def test_micro_batch_quarantines_late_events():
    base = datetime(2026, 11, 20, 11, 0)
    from order_stream.streaming import MicroBatch

    batch = MicroBatch(1, base, [], late=[_event("ORD-LATE", base - timedelta(hours=2))])
    quality, _ = run_micro_batch(batch)
    assert [reason for _, reason in quality.quarantined] == ["late_event"]
