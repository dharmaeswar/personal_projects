"""Publish dashboard-ready datasets.

A publish writes the dataset into a partitioned output layout
(``publish/<dataset>/date=YYYY-MM-DD/part.jsonl``) plus a manifest that
records schema, row count, quality-gate result and metric versions.
The manifest is the one-source-of-truth pointer: consumers read the
latest manifest, never a hand-picked file.
"""

from __future__ import annotations

import json
import os
from datetime import date


def publish_dataset(rows: list[dict], dataset: str, out_root: str, day: date,
                    schema: list[str], gate_passed: bool,
                    metric_versions: dict[str, str]) -> dict:
    """Write the dataset partition + manifest. Returns the manifest dict."""
    partition_dir = os.path.join(out_root, dataset, f"date={day.isoformat()}")
    os.makedirs(partition_dir, exist_ok=True)
    part_path = os.path.join(partition_dir, "part.jsonl")
    with open(part_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({k: _jsonable(v) for k, v in row.items()}, sort_keys=True) + "\n")
    manifest = {
        "dataset": dataset,
        "partition": f"date={day.isoformat()}",
        "path": part_path,
        "schema": list(schema),
        "row_count": len(rows),
        "quality_gate_passed": gate_passed,
        "metric_versions": dict(metric_versions),
        "published_date": day.isoformat(),
    }
    manifest_path = os.path.join(partition_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    return value


def read_latest_manifest(out_root: str, dataset: str) -> dict:
    """Read the newest manifest for a dataset (latest partition wins)."""
    base = os.path.join(out_root, dataset)
    partitions = sorted(os.listdir(base))
    if not partitions:
        raise FileNotFoundError(f"no partitions published for {dataset}")
    latest = partitions[-1]
    with open(os.path.join(base, latest, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)
