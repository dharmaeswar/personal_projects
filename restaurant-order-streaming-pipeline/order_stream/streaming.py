"""Micro-batch streaming engine, mirroring Spark Structured Streaming.

A micro-batch is a bounded slice of the topic: events up to a watermark.
Events older than the watermark are late and are quarantined instead of
being silently dropped, the way a Structured Streaming job with
``withWatermark`` + a late-data sink behaves. Windowed aggregates are
15-minute tumbling windows per restaurant — the streaming equivalent of a
Spark ``groupBy(window, restaurant_id)`` aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from .events import OrderEvent
from .quality import QualityResult, cleanse


@dataclass
class MicroBatch:
    batch_id: int
    watermark: datetime
    events: list[OrderEvent]
    late: list[OrderEvent] = field(default_factory=list)


def window_start(event_time: datetime, minutes: int = 15) -> datetime:
    """Floor an event time to its tumbling-window start."""
    return event_time.replace(
        minute=(event_time.minute // minutes) * minutes, second=0, microsecond=0
    )


def split_batches(events: list[OrderEvent], watermark_lag: timedelta = timedelta(minutes=30),
                  batch_size: int = 40) -> list[MicroBatch]:
    """Split arrival-ordered events into micro-batches with a running watermark.

    The watermark is the newest event time seen in earlier batches minus
    ``watermark_lag``. An event whose event time is at or before the
    watermark when its batch is processed arrived late (delayed in transit)
    and is split off for quarantine, the way a Structured Streaming job
    with ``withWatermark`` + a late-data sink behaves.
    """
    batches: list[MicroBatch] = []
    running_max: datetime | None = None
    batch_id = 0
    for i in range(0, len(events), batch_size):
        chunk = events[i:i + batch_size]
        watermark = (running_max - watermark_lag) if running_max else None
        late = [e for e in chunk if watermark is not None and e.event_time <= watermark]
        on_time = [e for e in chunk if e not in late]
        batches.append(MicroBatch(
            batch_id,
            watermark or max(e.event_time for e in chunk),
            on_time, late,
        ))
        chunk_max = max(e.event_time for e in chunk)
        running_max = chunk_max if running_max is None else max(running_max, chunk_max)
        batch_id += 1
    return batches


def run_micro_batch(batch: MicroBatch) -> tuple[QualityResult, pd.DataFrame]:
    """Cleanse one micro-batch and compute its windowed aggregates.

    Returns the quality result (clean + quarantined rows, late events added
    to quarantine with reason ``late_event``) and a DataFrame of per-window
    aggregates: orders, items, revenue per restaurant per 15-minute window.
    """
    quality = cleanse(batch.events)
    for event in batch.late:
        quality.quarantined.append((event, "late_event"))
    rows = [
        {
            "window_start": window_start(e.event_time),
            "restaurant_id": e.restaurant_id,
            "orders": 1,
            "items": e.quantity,
            "revenue": e.total_amount,
        }
        for e in quality.clean
    ]
    if not rows:
        agg = pd.DataFrame(columns=["window_start", "restaurant_id", "orders", "items", "revenue"])
    else:
        agg = (
            pd.DataFrame(rows)
            .groupby(["window_start", "restaurant_id"], as_index=False)
            .agg({"orders": "sum", "items": "sum", "revenue": "sum"})
        )
    return quality, agg
