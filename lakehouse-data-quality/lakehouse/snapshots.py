"""Iceberg-style table snapshots: versioning, time travel, schema evolution.

Each commit writes an immutable snapshot file
``snapshots/snapshot-<id>.parquet`` plus a manifest entry in
``snapshots.json`` (snapshot id, parent id, operation, schema version,
row count, columns). Reading is by snapshot id, so any earlier state of
a table can be read back — time travel — and a failed write never
touches the registry, so it can never be observed as committed.

Schema evolution is backwards compatible: ``evolve_schema`` adds a
nullable column with a default value, bumps the schema version, and
records the change in the new snapshot. Old snapshots keep their old
schema and still read exactly as they were written.

This runs locally with pandas + Parquet — no Iceberg runtime is
involved — and mirrors the Iceberg concepts (snapshot chain, manifest,
schema evolution, time travel) rather than claiming a cluster run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REGISTRY = "snapshots.json"


def _registry_path(table_dir: Path) -> Path:
    return table_dir / REGISTRY


def _snapshots_dir(table_dir: Path) -> Path:
    return table_dir / "snapshots"


def list_snapshots(table_dir: Path) -> list[dict]:
    """Return the snapshot registry (empty if the table has no snapshots)."""
    path = _registry_path(table_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _schema_version(table_dir: Path) -> int:
    snapshots = list_snapshots(table_dir)
    return snapshots[-1]["schema_version"] if snapshots else 1


def commit_snapshot(
    df: pd.DataFrame, table_dir: Path, operation: str
) -> dict:
    """Commit ``df`` as a new immutable snapshot; return its manifest entry.

    The snapshot file is written before the registry is updated, so a
    crash mid-write leaves the previous snapshot as the current one.
    """
    table_dir.mkdir(parents=True, exist_ok=True)
    snapshots = list_snapshots(table_dir)
    snapshot_id = len(snapshots) + 1
    parent_id = snapshots[-1]["snapshot_id"] if snapshots else None
    _snapshots_dir(table_dir).mkdir(parents=True, exist_ok=True)
    file_name = f"snapshot-{snapshot_id}.parquet"
    df.to_parquet(_snapshots_dir(table_dir) / file_name, index=False)
    entry = {
        "snapshot_id": snapshot_id,
        "parent_id": parent_id,
        "operation": operation,
        "schema_version": _schema_version(table_dir),
        "rows": len(df),
        "columns": list(df.columns),
        "file": f"snapshots/{file_name}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    snapshots.append(entry)
    _registry_path(table_dir).write_text(json.dumps(snapshots, indent=2))
    return entry


def read_snapshot(table_dir: Path, snapshot_id: int) -> pd.DataFrame:
    """Time travel: read the table exactly as it was at ``snapshot_id``."""
    snapshots = list_snapshots(table_dir)
    entry = next((s for s in snapshots if s["snapshot_id"] == snapshot_id), None)
    if entry is None:
        raise ValueError(f"no snapshot {snapshot_id} for table {table_dir}")
    return pd.read_parquet(table_dir / entry["file"])


def current_snapshot(table_dir: Path) -> dict | None:
    """Return the latest snapshot entry, or None if the table is empty."""
    snapshots = list_snapshots(table_dir)
    return snapshots[-1] if snapshots else None


def evolve_schema(
    df: pd.DataFrame,
    table_dir: Path,
    new_column: str,
    default: object,
    operation: str,
) -> dict:
    """Add a nullable column with a default value and commit a new snapshot.

    The schema version bumps by one; the new column is present from this
    snapshot onward, and earlier snapshots still read with their old
    columns only. Adding a column never rewrites history.
    """
    if new_column in df.columns:
        raise ValueError(f"column {new_column!r} already exists")
    out = df.copy()
    out[new_column] = default
    snapshots = list_snapshots(table_dir)
    snapshot_id = len(snapshots) + 1
    parent_id = snapshots[-1]["snapshot_id"] if snapshots else None
    _snapshots_dir(table_dir).mkdir(parents=True, exist_ok=True)
    file_name = f"snapshot-{snapshot_id}.parquet"
    out.to_parquet(_snapshots_dir(table_dir) / file_name, index=False)
    entry = {
        "snapshot_id": snapshot_id,
        "parent_id": parent_id,
        "operation": operation,
        "schema_version": _schema_version(table_dir) + 1,
        "rows": len(out),
        "columns": list(out.columns),
        "file": f"snapshots/{file_name}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    snapshots.append(entry)
    _registry_path(table_dir).write_text(json.dumps(snapshots, indent=2))
    return entry
