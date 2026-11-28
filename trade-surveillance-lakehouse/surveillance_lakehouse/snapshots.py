"""Iceberg-style snapshot log.

Every table write appends a versioned snapshot entry (snapshot id,
parent snapshot, operation, rows added/removed, timestamp) to
``_snapshots.json`` next to the table. A reader can trace any table
back to the write that produced it, and a bad write can be rolled back
to its parent snapshot. This is the bookkeeping pattern Apache Iceberg
uses; it runs here as plain JSON, not an Iceberg runtime.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def record_snapshot(table_dir: Path, operation: str,
                    rows_added: int, rows_removed: int = 0) -> dict:
    """Append a snapshot entry for one table write. Returns the entry."""
    table_dir.mkdir(parents=True, exist_ok=True)
    log_path = table_dir / "_snapshots.json"
    entries = []
    if log_path.exists():
        entries = json.loads(log_path.read_text())
    parent = entries[-1]["snapshot_id"] if entries else None
    entry = {
        "version": len(entries) + 1,
        "snapshot_id": uuid.uuid4().hex[:16],
        "parent_snapshot_id": parent,
        "operation": operation,
        "rows_added": rows_added,
        "rows_removed": rows_removed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    log_path.write_text(json.dumps(entries, indent=2))
    return entry


def read_snapshots(table_dir: Path) -> list[dict]:
    """Read the snapshot log for a table (empty list when none exists)."""
    log_path = table_dir / "_snapshots.json"
    if not log_path.exists():
        return []
    return json.loads(log_path.read_text())
