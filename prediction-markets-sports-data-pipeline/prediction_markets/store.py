"""Partitioned columnar store for cleansed market data.

Numeric columns are stored per (event, date) partition as NumPy ``.npz``
files — one array per column, which is the columnar layout a production
Parquet/Iceberg table would use (Parquet is the stated production target;
``.npz`` keeps this project dependency-light while preserving the
columnar, partition-pruned read pattern). A manifest CSV lists every
partition with its row count and time range. Reads are point-in-time:
``read_asof(event_id, ts)`` returns only rows at or before ``ts``, so a
backtest can never see the future.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

import numpy as np

from .cleanse import CleanRecord

MANIFEST_FIELDS = ("event_id", "date", "path", "rows", "min_ts", "max_ts")


def partition_path(root: str, event_id: str, date: str) -> str:
    return os.path.join(root, f"event_id={event_id}", f"date={date}", "data.npz")


def write_store(records: list[CleanRecord], root: str) -> list[dict]:
    """Write records into partitions; return the manifest rows."""
    by_part: dict[tuple, list[CleanRecord]] = {}
    for rec in records:
        by_part.setdefault((rec.event_id, rec.ts.date().isoformat()), []).append(rec)
    manifest: list[dict] = []
    for (event_id, date), rows in sorted(by_part.items()):
        rows = sorted(rows, key=lambda r: (r.ts, r.book))
        path = partition_path(root, event_id, date)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez_compressed(
            path,
            ts=np.array([r.ts.timestamp() for r in rows], dtype=np.float64),
            fair_home=np.array([r.fair_home for r in rows], dtype=np.float64),
            fair_away=np.array([r.fair_away for r in rows], dtype=np.float64),
            overround=np.array([r.overround for r in rows], dtype=np.float64),
            book=np.array([r.book for r in rows]),
        )
        manifest.append({
            "event_id": event_id, "date": date,
            "path": os.path.relpath(path, root), "rows": len(rows),
            "min_ts": min(r.ts for r in rows).isoformat(),
            "max_ts": max(r.ts for r in rows).isoformat(),
        })
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "manifest.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest)
    return manifest


def read_partition(root: str, rel_path: str) -> list[CleanRecord]:
    with np.load(os.path.join(root, rel_path), allow_pickle=True) as data:
        books = [str(b) for b in data["book"]]
        event_id = rel_path.split(os.sep)[0].split("=", 1)[1]
        return [
            CleanRecord(
                event_id=event_id, book=books[i],
                ts=datetime.fromtimestamp(float(data["ts"][i]), tz=timezone.utc),
                fair_home=float(data["fair_home"][i]),
                fair_away=float(data["fair_away"][i]),
                overround=float(data["overround"][i]),
            )
            for i in range(len(data["ts"]))
        ]


def read_asof(root: str, event_id: str, asof: datetime) -> list[CleanRecord]:
    """All stored rows for one event at or before ``asof`` (no look-ahead)."""
    manifest_path = os.path.join(root, "manifest.csv")
    out: list[CleanRecord] = []
    with open(manifest_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["event_id"] != event_id:
                continue
            if datetime.fromisoformat(row["min_ts"]) > asof:
                continue
            out.extend(r for r in read_partition(root, row["path"]) if r.ts <= asof)
    return sorted(out, key=lambda r: (r.ts, r.book))


def read_all(root: str) -> list[CleanRecord]:
    manifest_path = os.path.join(root, "manifest.csv")
    out: list[CleanRecord] = []
    with open(manifest_path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.extend(read_partition(root, row["path"]))
    return sorted(out, key=lambda r: (r.event_id, r.ts, r.book))
