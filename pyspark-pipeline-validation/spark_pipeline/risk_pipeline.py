"""Risk-technology ETL: raw -> cleansed -> curated (partitioned) -> gold aggregates,
plus an agentic-AI-assisted triage of the quarantined rows.

Stages mirror a Spark batch job on Databricks:
  raw        raw ingest, stored as Parquet, nothing cleaned
  cleansed   deduplicated + quality-filtered, schema enforced
  quarantine every rejected row, kept with its violation rule
  curated    cleansed rows written partitioned by trade_date
  gold       daily notional / exposure by date / book, reconciled to cleansed
  triage     the agent reviews each quarantined row and proposes a disposition
"""
from pathlib import Path

import pandas as pd

from .agentic_quality import triage_quarantine, triage_summary
from .risk_data import generate_risk_raw
from .risk_transforms import (
    aggregate_risk_daily,
    dedupe_latest_risk,
    filter_valid_risk,
    join_book_dim,
    reconcile_risk,
    with_derived_risk_columns,
)


def run_risk_pipeline(out_dir):
    out_dir = Path(out_dir)
    tables = out_dir / "risk_tables"
    tables.mkdir(parents=True, exist_ok=True)

    raw = generate_risk_raw()
    raw.to_parquet(tables / "raw.parquet", index=False)

    deduped, n_duplicates = dedupe_latest_risk(raw)
    valid, invalid = filter_valid_risk(deduped)
    cleansed = join_book_dim(valid)
    cleansed = with_derived_risk_columns(cleansed)

    cleansed.to_parquet(tables / "cleansed.parquet", index=False)
    invalid.to_parquet(tables / "quarantine.parquet", index=False)
    # Partitioned write: one directory per trade_date, like partitionBy("trade_date").
    cleansed.to_parquet(tables / "curated", partition_cols=["trade_date"], index=False)

    gold = aggregate_risk_daily(cleansed)
    gold.to_parquet(tables / "gold.parquet", index=False)
    reconciliation = reconcile_risk(cleansed, gold)

    findings = triage_quarantine(invalid)
    triage = triage_summary(findings)

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
        "total_notional": round(float(cleansed["notional"].sum()), 2),
        "total_exposure": round(float(cleansed["exposure"].sum()), 2),
        "reconciliation_passed": reconciliation["passed"],
        "violation_counts": violation_counts,
        "triage": triage,
    }
    return summary, findings, invalid


def render_risk_report(summary, findings, invalid):
    lines = [
        "PySpark Pipeline Validation — risk-technology ETL run report",
        f"Raw rows: {summary['raw_rows']}",
        f"Duplicates removed (window dedup): {summary['duplicates_removed']}",
        f"Quarantined rows: {summary['quarantined_rows']}",
        f"Cleansed rows: {summary['cleansed_rows']}",
        f"Gold aggregate rows: {summary['gold_rows']}",
        f"Curated partitions (by trade_date): {summary['partitions']}",
        f"Total cleansed notional: ${summary['total_notional']:,.2f}",
        f"Total cleansed exposure: ${summary['total_exposure']:,.2f}",
        f"Reconciliation gold vs cleansed: {'PASS' if summary['reconciliation_passed'] else 'FAIL'}",
        "",
        "Violations quarantined:",
    ]
    for rule, count in sorted(summary["violation_counts"].items()):
        lines.append(f"  {rule}: {count}")
    lines += ["", "Agentic-AI triage of quarantined rows (rule-based policy agent):"]
    for disposition, count in sorted(summary["triage"].items()):
        lines.append(f"  {disposition}: {count}")
    for finding in findings:
        fixed = (
            f" corrected_exposure={finding['corrected_exposure']:,.2f}"
            if finding["corrected_exposure"] is not None
            else ""
        )
        lines.append(
            f"  {finding['trade_id']}: {finding['violation']} -> "
            f"{finding['disposition']} ({finding['confidence']} confidence){fixed}"
        )
        lines.append(f"    action: {finding['action']}")
    lines += ["", "Quarantined trade_ids:"]
    for trade_id, violation in zip(invalid["trade_id"], invalid["violation"]):
        lines.append(f"  {trade_id}: {violation}")
    return "\n".join(lines) + "\n"
