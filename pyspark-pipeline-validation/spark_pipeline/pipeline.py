"""Batch pipeline: raw -> cleansed -> curated (partitioned) -> gold aggregates.

Stages mirror a Spark batch job:
  raw        raw ingest, stored as Parquet, nothing cleaned
  cleansed   deduplicated + quality-filtered, schema enforced
  quarantine every rejected row, kept with its violation rule
  curated    cleansed rows written partitioned by event_date
  gold       daily revenue by date / region / category, reconciled to cleansed
"""
from pathlib import Path

import pandas as pd

from .checks import run_quality_checks
from .data import generate_raw
from .schema import enforce_schema
from .transforms import (
    aggregate_daily,
    dedupe_latest,
    filter_valid,
    join_product_dim,
    reconcile,
    with_derived_columns,
)


def run_pipeline(out_dir):
    out_dir = Path(out_dir)
    tables = out_dir / "pipeline_tables"
    tables.mkdir(parents=True, exist_ok=True)

    raw = generate_raw()
    raw.to_parquet(tables / "raw.parquet", index=False)

    deduped, n_duplicates = dedupe_latest(raw)
    valid, invalid = filter_valid(deduped)
    cleansed = join_product_dim(valid)
    cleansed = with_derived_columns(cleansed)
    enforce_schema(cleansed.drop(columns=["product_category", "amount_band", "is_high_value"]))

    cleansed.to_parquet(tables / "cleansed.parquet", index=False)
    invalid.to_parquet(tables / "quarantine.parquet", index=False)
    # Partitioned write: one directory per event_date, like partitionBy("event_date").
    cleansed.to_parquet(tables / "curated", partition_cols=["event_date"], index=False)

    gold = aggregate_daily(cleansed)
    gold.to_parquet(tables / "gold.parquet", index=False)
    reconciliation = reconcile(cleansed, gold)
    checks = run_quality_checks(cleansed, gold, reconciliation)

    partitions = sorted(p.name for p in (tables / "curated").iterdir() if p.is_dir())
    violation_counts = (
        invalid["violation"].str.split("+", regex=False).str[0].value_counts().to_dict()
        if len(invalid) else {}
    )
    summary = {
        "raw_rows": len(raw),
        "duplicates_removed": n_duplicates,
        "quarantined_rows": len(invalid),
        "cleansed_rows": len(cleansed),
        "gold_rows": len(gold),
        "partitions": len(partitions),
        "violation_counts": violation_counts,
        "checks_passed": sum(1 for _, s, _ in checks if s == "PASS"),
        "checks_total": len(checks),
        "reconciliation_passed": reconciliation["passed"],
        "total_revenue": round(float(cleansed["amount"].sum()), 2),
    }
    return summary, checks, invalid
