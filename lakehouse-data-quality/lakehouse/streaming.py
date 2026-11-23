"""Micro-batch streaming ingest, in the spirit of Spark Structured Streaming.

An append-only event stream arrives in micro-batches. Each batch is
processed exactly once: events are deduplicated on ``event_id`` (the
idempotency key, as in a Delta ``MERGE`` on the event id), and events
older than the watermark are dropped as late data instead of silently
rewriting history.

This runs locally with pandas — no Spark cluster is involved — so every
operation names the Structured Streaming operation it mirrors:

- micro-batch trigger          -> ``process_micro_batch`` per batch
- watermark (event-time skew)   -> ``watermark`` on the checkpoint
- exactly-once via idempotency  -> dedup on ``event_id`` against the
                                   checkpoint's processed ids
- checkpoint / offset tracking  -> :class:`StreamCheckpoint`
- late data                     -> dropped to a late-data frame with a
                                   reason, never merged into bronze

All event data is synthetic and seeded. Nothing here is a claim about
any real institution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

DEFAULT_LATENESS_MINUTES = 10


@dataclass
class StreamCheckpoint:
    """Offset + watermark state, as a Structured Streaming checkpoint."""

    last_offset: int = -1
    watermark: pd.Timestamp | None = None
    processed_event_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "last_offset": self.last_offset,
            "watermark": None if self.watermark is None else self.watermark.isoformat(),
            "processed_event_ids": sorted(self.processed_event_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "StreamCheckpoint":
        watermark = payload.get("watermark")
        return cls(
            last_offset=int(payload.get("last_offset", -1)),
            watermark=None if watermark is None else pd.Timestamp(watermark),
            processed_event_ids=set(payload.get("processed_event_ids", [])),
        )


def generate_event_stream(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Synthetic order-event stream with planted late events and duplicates.

    120 events: 3 are duplicates of earlier event ids, 2 arrive with an
    event time older than the watermark will allow (late data). Offsets
    are assigned in arrival order, so a re-run sees the same stream.
    """
    rng = np.random.default_rng(seed)
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    customers = [f"C{i:04d}" for i in range(1, 41)]
    products = [f"P{i:03d}" for i in range(1, 13)]
    quantities = rng.integers(1, 10, size=n)
    prices = np.round(rng.uniform(5.0, 250.0, size=n), 2)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"E{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "order_id": [f"O{i:05d}" for i in range(n)],
            "customer_id": rng.choice(customers, size=n),
            "product_id": rng.choice(products, size=n),
            "quantity": quantities,
            "unit_price": prices,
            "total_amount": np.round(quantities * prices, 2),
            "region": rng.choice(["Northeast", "Midwest", "South", "West"], size=n),
        }
    )
    # 3 duplicate deliveries of earlier events (same event_id, new offset).
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    # 2 late events: event time 3 hours before the stream starts.
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = ["E90001", "E90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def split_micro_batches(stream: pd.DataFrame, batch_size: int = 40) -> list[pd.DataFrame]:
    """Split the stream into consecutive micro-batches by offset order."""
    ordered = stream.sort_values("offset").reset_index(drop=True)
    return [ordered.iloc[i : i + batch_size].copy() for i in range(0, len(ordered), batch_size)]


def process_micro_batch(
    batch: pd.DataFrame,
    checkpoint: StreamCheckpoint,
    allowed_lateness_minutes: int = DEFAULT_LATENESS_MINUTES,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StreamCheckpoint]:
    """Process one micro-batch; return (accepted, late, duplicates, checkpoint).

    Rules, in order: skip offsets already processed; drop event ids
    already seen (duplicates — exactly-once comes first, so a
    re-delivery is never also counted as late data); drop events older
    than the watermark (late data); accept the rest and advance the
    watermark to the max event time seen minus the allowed lateness.
    The watermark only moves forward.
    """
    new = batch[batch["offset"] > checkpoint.last_offset].copy()
    if new.empty:
        return new, new.iloc[0:0], new.iloc[0:0], checkpoint
    is_dup = new["event_id"].isin(checkpoint.processed_event_ids)
    duplicates = new[is_dup].copy()
    unseen = new[~is_dup].copy()
    if checkpoint.watermark is not None:
        is_late = unseen["event_time"] < checkpoint.watermark
    else:
        is_late = pd.Series(False, index=unseen.index)
    late = unseen[is_late].copy()
    accepted = unseen[~is_late].copy()
    max_event_time = pd.to_datetime(new["event_time"]).max()
    candidate = max_event_time - timedelta(minutes=allowed_lateness_minutes)
    watermark = candidate if checkpoint.watermark is None else max(checkpoint.watermark, candidate)
    new_checkpoint = StreamCheckpoint(
        last_offset=int(new["offset"].max()),
        watermark=watermark,
        processed_event_ids=checkpoint.processed_event_ids | set(accepted["event_id"]),
    )
    return accepted, late, duplicates, new_checkpoint


def run_stream(
    stream: pd.DataFrame, batch_size: int = 40, allowed_lateness_minutes: int = DEFAULT_LATENESS_MINUTES
) -> dict:
    """Process the whole stream batch by batch; return accepted rows + stats."""
    checkpoint = StreamCheckpoint()
    accepted_parts: list[pd.DataFrame] = []
    late_parts: list[pd.DataFrame] = []
    dup_parts: list[pd.DataFrame] = []
    batch_stats = []
    for i, batch in enumerate(split_micro_batches(stream, batch_size)):
        accepted, late, duplicates, checkpoint = process_micro_batch(
            batch, checkpoint, allowed_lateness_minutes
        )
        accepted_parts.append(accepted)
        late_parts.append(late)
        dup_parts.append(duplicates)
        batch_stats.append(
            {
                "batch": i,
                "arrived": len(batch),
                "accepted": len(accepted),
                "late_dropped": len(late),
                "duplicates_dropped": len(duplicates),
                "watermark": None if checkpoint.watermark is None else checkpoint.watermark.isoformat(),
            }
        )
    accepted_all = pd.concat(accepted_parts, ignore_index=True) if accepted_parts else pd.DataFrame()
    late_all = pd.concat(late_parts, ignore_index=True) if late_parts else pd.DataFrame()
    dup_all = pd.concat(dup_parts, ignore_index=True) if dup_parts else pd.DataFrame()
    return {
        "accepted": accepted_all,
        "late": late_all,
        "duplicates": dup_all,
        "batches": batch_stats,
        "checkpoint": checkpoint,
        "total_arrived": len(stream),
    }
