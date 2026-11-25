"""Iceberg-style table maintenance: partition specs, compaction, and
snapshot expiry.

Three ideas, modelled on how a lakehouse table format keeps a table
healthy over time:

- Partition spec: how rows map to partitions (identity, day-truncated
  event time, bucketed hash). The spec decides which files a query
  has to read, so it is a cost decision, not just an organisation one.
- Compaction: many small files make every query pay a planning and
  open cost. Merge-on-read keeps the old files and adds a compacted
  view (cheap, safe, readers see both); copy-on-write rewrites the
  files and swaps them in one commit (cleaner, but a failed rewrite
  leaves work to clean up). The planner picks based on file size and
  count, and says why.
- Snapshot expiry: old snapshots are kept only as long as time travel
  needs them; expiring the rest frees storage and bounds the manifest.

Everything runs locally on file metadata — no Iceberg runtime is
involved — and the code says so where it matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

SMALL_FILE_BYTES = 8 * 1024 * 1024  # 8 MiB: below this, a file is "small"
MIN_FILES_TO_COMPACT = 4


@dataclass
class TableFile:
    path: str
    rows: int
    size_bytes: int
    partition: str


@dataclass
class CompactionPlan:
    strategy: str  # "merge-on-read" or "copy-on-write" or "none"
    files_to_compact: list[TableFile]
    estimated_new_files: int
    reason: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return (
            f"{self.strategy}: compact {len(self.files_to_compact)} files "
            f"into ~{self.estimated_new_files} ({self.reason})"
        )


def partition_value(
    spec: str, value: object, num_buckets: int = 16
) -> str:
    """Map one value to its partition label under a partition spec.

    Supported specs: ``identity`` (the value itself), ``day`` (the
    calendar day of a timestamp), ``bucket[N]`` (hash bucket 0..N-1).
    """
    if spec == "identity":
        return str(value)
    if spec == "day":
        ts = pd.Timestamp(value)
        return ts.strftime("%Y-%m-%d")
    if spec.startswith("bucket[") and spec.endswith("]"):
        n = int(spec[len("bucket[") : -1])
        if n < 1:
            raise ValueError("bucket count must be at least 1")
        return str(abs(hash(str(value))) % n)
    raise ValueError(f"unknown partition spec: {spec}")


def plan_compaction(
    files: list[TableFile],
    strategy: str = "merge-on-read",
    small_file_bytes: int = SMALL_FILE_BYTES,
    min_files: int = MIN_FILES_TO_COMPACT,
) -> CompactionPlan:
    """Decide whether (and how) to compact a table's files.

    Only small files are candidates. Fewer than ``min_files`` small
    files is not worth a compaction run. Merge-on-read is the default:
    it never rewrites data in place, so a failed run is harmless.
    Copy-on-write is chosen only when the caller asks for it and the
    table is dominated by small files — the rewrite is worth it then,
    and the plan says so.
    """
    if strategy not in ("merge-on-read", "copy-on-write"):
        raise ValueError(f"unknown compaction strategy: {strategy}")
    small = [f for f in files if f.size_bytes < small_file_bytes]
    if len(small) < min_files:
        return CompactionPlan(
            strategy="none",
            files_to_compact=[],
            estimated_new_files=0,
            reason=(
                f"only {len(small)} small files (need {min_files}) — "
                "compaction would cost more than it saves"
            ),
        )
    total_bytes = sum(f.size_bytes for f in small)
    target_files = max(1, total_bytes // (64 * 1024 * 1024))
    if strategy == "copy-on-write" and len(small) >= 2 * min_files:
        reason = (
            f"{len(small)} of {len(files)} files are small; a full rewrite "
            "clears the small-file debt in one commit"
        )
    else:
        strategy = "merge-on-read"
        reason = (
            f"{len(small)} small files totalling {total_bytes} bytes; "
            "merge-on-read keeps old files until readers move over"
        )
    return CompactionPlan(
        strategy=strategy,
        files_to_compact=small,
        estimated_new_files=target_files,
        reason=reason,
    )


def expire_snapshots(
    snapshots: list[dict], retain: int = 5
) -> tuple[list[dict], list[dict]]:
    """Keep the newest ``retain`` snapshots; return (kept, expired).

    Snapshots are ordered oldest-first, as the snapshot registry
    stores them. Expiring old snapshots bounds manifest size and
    storage; time travel only reaches back as far as the retained set.
    """
    if retain < 1:
        raise ValueError("retain must be at least 1")
    if len(snapshots) <= retain:
        return list(snapshots), []
    return snapshots[-retain:], snapshots[:-retain]


def table_health_summary(files: list[TableFile]) -> dict:
    """One-line health numbers for a table: file count, small-file share, size."""
    total_bytes = sum(f.size_bytes for f in files)
    small = sum(1 for f in files if f.size_bytes < SMALL_FILE_BYTES)
    return {
        "files": len(files),
        "rows": sum(f.rows for f in files),
        "total_bytes": total_bytes,
        "small_files": small,
        "small_file_share": (small / len(files)) if files else 0.0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
