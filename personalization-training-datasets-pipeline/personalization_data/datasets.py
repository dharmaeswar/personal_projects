"""Time-based splits, medallion writes, and dataset versioning.

Training rows are split by impression date (train / validation / test) so
no future impression leaks into training — random splits would overstate
model quality on a time-ordered personalization problem.

Medallion layout (Delta Lake on Databricks in production, Parquet here):
bronze = raw events as ingested, silver = cleansed events, gold = the
versioned training dataset plus a feature-store snapshot.

Spark equivalents: ``df.write.partitionBy("event_date").format("delta")``
and Delta Lake time travel / ``DESCRIBE HISTORY`` for versioning.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def time_split(rows: pd.DataFrame, train_days: int = 10, val_days: int = 2,
               start: str = "2026-11-01") -> dict[str, pd.DataFrame]:
    """Split training rows by impression date: first N days train, next val, rest test."""
    base = pd.Timestamp(start)
    train_end = base + pd.Timedelta(days=train_days)
    val_end = train_end + pd.Timedelta(days=val_days)
    ts = pd.to_datetime(rows["impression_ts"])
    return {
        "train": rows[ts < train_end].reset_index(drop=True),
        "validation": rows[(ts >= train_end) & (ts < val_end)].reset_index(drop=True),
        "test": rows[ts >= val_end].reset_index(drop=True),
    }


def dataset_fingerprint(rows: pd.DataFrame, config: dict) -> str:
    """Stable hash of the training set contents + build config (reproducibility)."""
    keys = "".join(sorted(
        f"{r.user_id}|{r.content_id}|{r.impression_ts.isoformat()}"
        for r in rows.itertuples(index=False)
    ))
    payload = keys + json.dumps(config, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_medallion(raw: pd.DataFrame, clean: pd.DataFrame,
                    training_rows: pd.DataFrame, out_dir: str | Path,
                    version: str = "v1") -> dict:
    """Write bronze / silver / gold Parquet layers and a version manifest."""
    out = Path(out_dir)
    (out / "bronze").mkdir(parents=True, exist_ok=True)
    (out / "silver").mkdir(parents=True, exist_ok=True)
    (out / "gold").mkdir(parents=True, exist_ok=True)

    bronze = raw.copy()
    bronze["event_date"] = pd.to_datetime(bronze["event_ts"]).dt.date.astype(str)
    bronze.to_parquet(out / "bronze" / "events.parquet", partition_cols=["event_date"])
    silver = clean.copy()
    silver["event_date"] = pd.to_datetime(silver["event_ts"]).dt.date.astype(str)
    silver.to_parquet(out / "silver" / "events.parquet", partition_cols=["event_date"])
    gold = training_rows.copy()
    gold["impression_date"] = pd.to_datetime(gold["impression_ts"]).dt.date.astype(str)
    gold.to_parquet(out / "gold" / "training_dataset.parquet",
                    partition_cols=["impression_date"])

    config = {"version": version, "horizon_hours": 24, "history_days": 7,
              "train_days": 10, "val_days": 2}
    manifest = {
        "version": version,
        "fingerprint": dataset_fingerprint(training_rows, config),
        "config": config,
        "row_counts": {
            "bronze": len(raw),
            "silver": len(clean),
            "gold": len(training_rows),
        },
        "label_rates": {
            "completion_rate": round(float(training_rows["label_completed"].mean()), 4)
            if len(training_rows) else 0.0,
            "like_rate": round(float(training_rows["label_liked"].mean()), 4)
            if len(training_rows) else 0.0,
        },
    }
    (out / "gold" / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
