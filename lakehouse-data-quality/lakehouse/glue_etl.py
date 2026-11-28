"""AWS Glue-style ETL jobs landing in Iceberg-style snapshot tables.

A Glue job, as modelled here, reads raw files from an S3-style
partitioned layout (``<source>/date=YYYY-MM-DD/orders.parquet``),
applies the same cleaning the medallion pipeline applies (schema cast,
dedupe on the business key, quality checks with quarantine), and
commits the result as a new immutable snapshot of the target table
(see :mod:`lakehouse.snapshots`).

Job bookmarks make the job incremental: the bookmark file records the
last partition processed, so a re-run reads only partitions that
arrived since the previous run, and a re-run with no new partitions is
a no-op that commits nothing.

This runs locally with pandas + Parquet — no AWS Glue service, S3
bucket, Spark cluster or Iceberg runtime is involved — and mirrors the
Glue concepts (partitioned sources, job bookmarks, DynamicFrame-style
schema handling, quarantine of bad records) rather than claiming a
cloud run. The transform logic is the same code the medallion
pipeline uses, so a row the pipeline would quarantine is quarantined
here too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .pipeline import build_silver
from .snapshots import commit_snapshot, current_snapshot, list_snapshots


@dataclass
class GlueJobRun:
    """Outcome of one Glue job run."""

    job_name: str
    partitions_read: list[str]
    rows_read: int
    rows_loaded: int
    rows_quarantined: int
    snapshot_id: int | None
    bookmark: str | None
    status: str  # "loaded", "no_new_partitions"


@dataclass
class GlueJob:
    """A Glue-style ETL job: partitioned source, snapshot target."""

    name: str
    source_dir: Path
    target_table_dir: Path
    bookmark_path: Path
    quarantine_dir: Path

    def list_partitions(self) -> list[str]:
        """Return sorted ``date=YYYY-MM-DD`` partition names present."""
        if not self.source_dir.exists():
            return []
        return sorted(
            p.name
            for p in self.source_dir.iterdir()
            if p.is_dir() and p.name.startswith("date=") and (p / "orders.parquet").exists()
        )

    def read_bookmark(self) -> str | None:
        """Return the last processed partition, or None on a first run."""
        if not self.bookmark_path.exists():
            return None
        return json.loads(self.bookmark_path.read_text()).get("last_partition")

    def _write_bookmark(self, partition: str) -> None:
        self.bookmark_path.parent.mkdir(parents=True, exist_ok=True)
        self.bookmark_path.write_text(
            json.dumps(
                {
                    "job": self.name,
                    "last_partition": partition,
                    "updated": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
        )


def seed_partitions(
    source_dir: Path, frames: dict[str, pd.DataFrame]
) -> list[str]:
    """Write ``{partition: orders frame}`` as S3-style date partitions.

    Returns the partition names written, sorted. Each frame is written
    to ``<source_dir>/date=<partition>/orders.parquet``.
    """
    names = []
    for partition, df in sorted(frames.items()):
        part_dir = source_dir / f"date={partition}"
        part_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(part_dir / "orders.parquet", index=False)
        names.append(f"date={partition}")
    return names


def run_glue_job(
    job: GlueJob, customers: pd.DataFrame, products: pd.DataFrame
) -> GlueJobRun:
    """Run the job over partitions newer than the bookmark.

    New partitions are concatenated, cleaned with ``build_silver``
    (dedupe, schema cast, quality checks, quarantine), and committed
    as one new snapshot of the target table. A run with no new
    partitions commits nothing and leaves the bookmark untouched.
    """
    bookmark = job.read_bookmark()
    partitions = [p for p in job.list_partitions() if bookmark is None or p > bookmark]
    if not partitions:
        return GlueJobRun(
            job_name=job.name,
            partitions_read=[],
            rows_read=0,
            rows_loaded=0,
            rows_quarantined=0,
            snapshot_id=None,
            bookmark=bookmark,
            status="no_new_partitions",
        )
    frames = [
        pd.read_parquet(job.source_dir / p / "orders.parquet") for p in partitions
    ]
    raw = pd.concat(frames, ignore_index=True)
    silver, quarantine = build_silver(raw, customers, products)
    # Append to the current snapshot state so the table is cumulative
    # across runs instead of being replaced by the latest batch.
    current = current_snapshot(job.target_table_dir)
    if current is not None:
        from .snapshots import read_snapshot

        previous = read_snapshot(job.target_table_dir, current["snapshot_id"])
        combined = pd.concat([previous, silver], ignore_index=True)
        combined = combined.drop_duplicates(subset=["order_id"], keep="first")
        combined = combined.reset_index(drop=True)
    else:
        combined = silver
    entry = commit_snapshot(combined, job.target_table_dir, f"glue job {job.name}")
    n_quarantined = len(quarantine)
    if n_quarantined:
        job.quarantine_dir.mkdir(parents=True, exist_ok=True)
        q_path = job.quarantine_dir / "orders.parquet"
        if q_path.exists():
            old = pd.read_parquet(q_path)
            quarantine = pd.concat([old, quarantine], ignore_index=True)
        quarantine.to_parquet(q_path, index=False)
    job._write_bookmark(partitions[-1])
    return GlueJobRun(
        job_name=job.name,
        partitions_read=partitions,
        rows_read=len(raw),
        rows_loaded=len(silver),
        rows_quarantined=n_quarantined,
        snapshot_id=entry["snapshot_id"],
        bookmark=partitions[-1],
        status="loaded",
    )


def render_job_report(run: GlueJobRun, snapshots: list[dict]) -> str:
    """Render a short text report for a job run."""
    lines = [
        f"Glue job: {run.job_name}",
        f"Status: {run.status}",
        f"Partitions read: {', '.join(run.partitions_read) or '(none)'}",
        f"Rows read: {run.rows_read}",
        f"Rows loaded: {run.rows_loaded}",
        f"Rows quarantined: {run.rows_quarantined}",
        f"Snapshot id: {run.snapshot_id if run.snapshot_id is not None else '(none)'}",
        f"Bookmark: {run.bookmark or '(none)'}",
        f"Snapshots in table: {len(snapshots)}",
    ]
    return "\n".join(lines) + "\n"
