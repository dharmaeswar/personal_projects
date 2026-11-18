"""Run the full advertising ETL pipeline and write the validation report.

Usage: python run_pipeline.py [--out DIR]
Writes the SQLite database to <out>/ads_etl.db, a transaction log to
<out>/pipeline_log.json, lineage to lineage.json, and a human-readable
validation_report.txt in the project root.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ads_etl.checks import check_late_arriving, check_reconciliation, run_all_checks
from ads_etl.data import generate_all
from ads_etl.monitoring import PipelineMetrics, StageTimer
from ads_etl.pipeline import (
    append_log,
    build_gold,
    build_silver,
    connect,
    load_bronze,
    read_log,
)
from ads_etl.report import render_report
from ads_etl.streaming import EventConsumer, consume_all_in_batches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ads_tables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    data = generate_all()
    campaigns, ads, bronze_events = data["campaigns"], data["ads"], data["events"]
    metrics = PipelineMetrics()

    # Stage 1: streaming-style ingest (in-memory consumer, batched commits).
    with StageTimer(metrics, "streaming ingest", len(bronze_events)) as timer:
        consumer = EventConsumer()
        consumer.produce(bronze_events)
        ingested = consume_all_in_batches(consumer, batch_size=100)
        timer.rows_out = len(ingested)
    print(f"ingested: {len(ingested)} events via consumer (offset {consumer.committed_offset})")

    # Stage 2: bronze load into SQLite.
    db_path = out / "ads_etl.db"
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    with StageTimer(metrics, "bronze load", len(ingested)) as timer:
        load_bronze(conn, campaigns, ads, ingested)
        timer.rows_out = len(ingested)
    log_path = out / "pipeline_log.json"
    if log_path.exists():
        log_path.unlink()
    append_log(log_path, "events_bronze", "bronze ingest", len(ingested), 0)
    print(f"bronze/events: {len(ingested)} rows")

    # Stage 3: bronze quality checks.
    with StageTimer(metrics, "bronze checks", len(ingested)) as timer:
        results = run_all_checks(ingested, ads, campaigns)
        timer.rows_out = len(ingested)
    failed = [r for r in results if not r.passed]
    print(f"bronze checks: {len(results) - len(failed)} of {len(results)} passed")

    # Stage 4: silver + quarantine, with lineage.
    with StageTimer(metrics, "silver build", len(ingested)) as timer:
        silver, quarantine, lineage = build_silver(conn, ingested, ads, campaigns)
        timer.rows_out = len(silver)
    append_log(log_path, "events_silver", "silver clean", len(silver), 0)
    append_log(log_path, "quarantine", "silver quarantine", len(quarantine), 0)
    late_rows = sum(r["late_arriving"] for r in silver)
    print(f"silver/events: {len(silver)} rows ({late_rows} late-arriving)")
    print(f"silver/quarantine: {len(quarantine)} rows")

    # Stage 5: gold aggregates via SQL.
    with StageTimer(metrics, "gold build", len(silver)) as timer:
        gold, gold_lineage = build_gold(conn, silver)
        timer.rows_out = len(gold)
    append_log(log_path, "gold_daily_spend", "gold aggregate", len(gold), 0)
    print(f"gold/daily_spend: {len(gold)} groups")

    reconciliation = check_reconciliation(silver, gold)
    late_check = check_late_arriving(ingested)
    metrics.bronze_rows = len(ingested)
    metrics.silver_rows = len(silver)
    metrics.quarantine_rows = len(quarantine)
    metrics.late_rows = late_rows
    metrics.gold_groups = len(gold)

    silver_spend = round(sum(r["spend_usd"] for r in silver), 2)
    gold_spend = round(sum(g["spend_usd"] for g in gold), 2)

    report = render_report(
        results,
        bronze_rows=len(ingested),
        silver_rows=len(silver),
        quarantine_rows=len(quarantine),
        late_rows=late_rows,
        gold_groups=len(gold),
        reconciliation=reconciliation,
        metrics=metrics,
        silver_spend=silver_spend,
        gold_spend=gold_spend,
    )
    (root / "validation_report.txt").write_text(report)
    (root / "lineage.json").write_text(
        json.dumps(
            {"silver_lineage": lineage, "gold_lineage": gold_lineage}, indent=2
        )
    )
    print()
    print(report)
    print(f"Late-arriving check: {late_check}")
    print("Transaction log versions:", len(read_log(log_path)))
    conn.close()


if __name__ == "__main__":
    main()
