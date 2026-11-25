"""Extraction from complex legacy source systems, in the spirit of a
data-lake ingestion layer.

Four source patterns, each modelled on the failure modes the real
connector has:

- Postgres replica under production load: watermark-based incremental
  extraction in capped batches, so a big table never hammers the
  replica. A resume watermark means a failed run restarts where it
  stopped instead of re-reading everything.
- Kafka consumer (KCL-style): per-shard sequence numbers, checkpointed
  offsets, at-least-once delivery — a reprocessed record is deduped
  on its id, never double-counted.
- AWS Lambda ingest: events arrive in batches; a partial batch
  failure retries only the failed records, not the whole batch.
- Third-party feeds: schema drift is detected before a bad feed lands
  (added / removed / type-changed columns), and a backfill planner
  turns a date range into chunked re-fetch windows.

Everything runs locally on synthetic data — no live Postgres, Kafka,
Lambda, or third-party feed is involved — and the code says so where
it matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_ROWS_PER_RUN = 10_000


@dataclass
class ReplicaExtract:
    """Result of one incremental replica extraction."""

    rows: pd.DataFrame
    new_watermark: pd.Timestamp | None
    rows_read: int
    batches: int
    truncated: bool  # True when the per-run row cap stopped the read early


def extract_from_replica(
    source: pd.DataFrame,
    watermark: pd.Timestamp | None,
    updated_at_col: str = "updated_at",
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_rows_per_run: int = DEFAULT_MAX_ROWS_PER_RUN,
) -> ReplicaExtract:
    """Read rows newer than ``watermark`` in capped batches.

    Rows are ordered by the watermark column so a resume after a
    failure re-reads only what was not committed. When the per-run cap
    is hit the extract stops early (``truncated=True``) and the caller
    schedules another run instead of overloading the replica.
    """
    ordered = source.sort_values(updated_at_col)
    if watermark is not None:
        ordered = ordered[ordered[updated_at_col] > watermark]
    total = len(ordered)
    take = min(total, max_rows_per_run)
    truncated = total > max_rows_per_run
    taken = ordered.iloc[:take]
    batches = (take + batch_size - 1) // batch_size if take else 0
    new_watermark = (
        taken[updated_at_col].max() if take else watermark
    )
    return ReplicaExtract(
        rows=taken.reset_index(drop=True),
        new_watermark=new_watermark,
        rows_read=take,
        batches=batches,
        truncated=truncated,
    )


@dataclass
class ShardCheckpoint:
    """Per-shard consumer offset, as a KCL lease/checkpoint would hold."""

    shard: str
    sequence_number: int = -1
    processed_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "shard": self.shard,
            "sequence_number": self.sequence_number,
            "processed_ids": sorted(self.processed_ids),
        }


@dataclass
class ConsumeResult:
    new_records: pd.DataFrame
    duplicates_skipped: int
    checkpoint: ShardCheckpoint
    lag: int  # records still behind the latest sequence number


def consume_shard(
    records: pd.DataFrame,
    checkpoint: ShardCheckpoint,
    sequence_col: str = "sequence_number",
    id_col: str = "event_id",
) -> ConsumeResult:
    """Consume records after the checkpoint, deduping reprocessed ids.

    At-least-once delivery means a crashed consumer re-reads its last
    batch; the id set makes the re-read a no-op instead of a duplicate.
    """
    ordered = records.sort_values(sequence_col)
    behind = ordered[ordered[sequence_col] > checkpoint.sequence_number]
    fresh = behind[~behind[id_col].isin(checkpoint.processed_ids)]
    duplicates = len(behind) - len(fresh)
    new_checkpoint = ShardCheckpoint(
        shard=checkpoint.shard,
        sequence_number=(
            int(ordered[sequence_col].max())
            if len(ordered)
            else checkpoint.sequence_number
        ),
        processed_ids=checkpoint.processed_ids | set(fresh[id_col]),
    )
    lag = int(len(ordered) - len(behind)) if len(ordered) else 0
    return ConsumeResult(
        new_records=fresh.reset_index(drop=True),
        duplicates_skipped=duplicates,
        checkpoint=new_checkpoint,
        lag=lag,
    )


@dataclass
class LambdaBatchResult:
    committed: pd.DataFrame
    failed: pd.DataFrame
    failed_reasons: list[str]


def ingest_lambda_events(
    events: pd.DataFrame,
    batch_size: int = 100,
    fail_on: set[str] | None = None,
    id_col: str = "event_id",
) -> LambdaBatchResult:
    """Ingest Lambda-delivered events in batches; retry only failures.

    ``fail_on`` lists event ids that fail validation on this pass (in a
    real run these are malformed payloads or throttled writes). Failed
    records are returned with their reasons so the caller retries just
    those, instead of replaying the whole batch.
    """
    fail_on = fail_on or set()
    committed_parts: list[pd.DataFrame] = []
    failed_parts: list[pd.DataFrame] = []
    reasons: list[str] = []
    for start in range(0, len(events), batch_size):
        batch = events.iloc[start : start + batch_size]
        bad = batch[batch[id_col].isin(fail_on)]
        good = batch[~batch[id_col].isin(fail_on)]
        if len(good):
            committed_parts.append(good)
        if len(bad):
            failed_parts.append(bad)
            reasons.extend(
                f"{event_id}: payload failed validation" for event_id in bad[id_col]
            )
    committed = (
        pd.concat(committed_parts, ignore_index=True)
        if committed_parts
        else events.iloc[0:0]
    )
    failed = (
        pd.concat(failed_parts, ignore_index=True)
        if failed_parts
        else events.iloc[0:0]
    )
    return LambdaBatchResult(
        committed=committed, failed=failed, failed_reasons=reasons
    )


@dataclass
class SchemaDrift:
    added_columns: list[str]
    removed_columns: list[str]
    type_changes: list[str]

    @property
    def has_drift(self) -> bool:
        return bool(self.added_columns or self.removed_columns or self.type_changes)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        parts = []
        if self.added_columns:
            parts.append(f"added: {', '.join(self.added_columns)}")
        if self.removed_columns:
            parts.append(f"removed: {', '.join(self.removed_columns)}")
        if self.type_changes:
            parts.append(f"type changed: {', '.join(self.type_changes)}")
        return "; ".join(parts) if parts else "no drift"


def detect_schema_drift(
    expected_schema: dict[str, str], observed: pd.DataFrame
) -> SchemaDrift:
    """Compare an observed feed frame against the expected schema."""
    observed_types = {col: str(dtype) for col, dtype in observed.dtypes.items()}
    added = [c for c in observed_types if c not in expected_schema]
    removed = [c for c in expected_schema if c not in observed_types]
    changed = [
        f"{c}: {expected_schema[c]} -> {observed_types[c]}"
        for c in expected_schema
        if c in observed_types and observed_types[c] != expected_schema[c]
    ]
    return SchemaDrift(
        added_columns=added, removed_columns=removed, type_changes=changed
    )


def plan_backfill(
    start: date, end: date, chunk_days: int = 7
) -> list[tuple[date, date]]:
    """Split a backfill range into chunked re-fetch windows.

    A failed or drifted feed is re-fetched in bounded windows so one
    bad day cannot stall the whole range, and a failed window can be
    retried on its own.
    """
    if end < start:
        raise ValueError("backfill end date is before its start date")
    if chunk_days < 1:
        raise ValueError("chunk_days must be at least 1")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=chunk_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows
