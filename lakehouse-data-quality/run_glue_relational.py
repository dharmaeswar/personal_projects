"""Run the Glue-style ETL + relational tuning demo end to end.

Usage: python run_glue_relational.py [--out DIR]
1. Seeds three daily bronze partitions (2026-11-15..17) from the
   project's seeded orders, with the usual planted violations in the
   middle partition.
2. Runs the Glue job twice: the first run loads the new partitions
   into an Iceberg-style snapshot table; the second run finds no new
   partitions (job bookmark) and commits nothing.
3. Loads the gold aggregates into a relational store (SQLite standing
   in for PostgreSQL/Aurora) and tunes one slow query — revenue by
   region and day — from a full table scan to an index search.
4. Validates the orders logical model and forward-engineers it to
   PostgreSQL and Aurora MySQL DDL.
Writes glue_relational_report.txt and glue_relational_report.json in
the project root. All data is synthetic and seeded; no AWS Glue
service, S3 bucket, Iceberg runtime, PostgreSQL server or Aurora
cluster is involved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lakehouse.data import generate_customers, generate_orders, generate_products, plant_violations
from lakehouse.glue_etl import GlueJob, render_job_report, run_glue_job, seed_partitions
from lakehouse.modeling import orders_model
from lakehouse.pipeline import build_gold
from lakehouse.relational import (
    RelationalStore,
    render_tuning_report,
    table_def_from_frame,
    tune_query,
)
from lakehouse.snapshots import current_snapshot, list_snapshots, read_snapshot

ROOT = Path(__file__).resolve().parent


def run_demo(root: Path) -> dict:
    out = root / "lakehouse_tables" / "glue_demo"
    out.mkdir(parents=True, exist_ok=True)
    customers = generate_customers()
    products = generate_products()

    # 1. Seed three daily bronze partitions; the middle one carries the
    # planted violations so the job's quarantine path is exercised.
    # Each partition gets its own order-id space (D15/D16/D17 prefix):
    # partitions are different days of new orders, not re-deliveries of
    # the same orders — re-delivery dedupe is covered by the tests.
    frames = {}
    for tag, seed in (("D15", 11), ("D16", 12), ("D17", 13)):
        df = generate_orders(seed=seed)
        df["order_id"] = tag + "-" + df["order_id"]
        if tag == "D16":
            df = plant_violations(df)
        frames[f"2026-11-{tag[1:]}"] = df
    partitions = seed_partitions(out / "bronze_orders", frames)

    job = GlueJob(
        name="orders-lakehouse-load",
        source_dir=out / "bronze_orders",
        target_table_dir=out / "silver_orders",
        bookmark_path=out / "bookmark.json",
        quarantine_dir=out / "quarantine",
    )
    first = run_glue_job(job, customers, products)
    second = run_glue_job(job, customers, products)

    # 2. Gold aggregates from the snapshot table, then into the
    # relational store with keys and an index to tune.
    silver = read_snapshot(job.target_table_dir, current_snapshot(job.target_table_dir)["snapshot_id"])
    gold = build_gold(silver, products)
    store = RelationalStore(out / "relational.db")
    try:
        gold_def = table_def_from_frame(
            "fact_daily_revenue",
            gold,
            primary_key=["order_date", "category", "region"],
            indexes=[["region", "order_date"]],
        )
        store.load_table(gold_def, gold)
        sql = (
            "SELECT order_date, SUM(total_revenue) FROM fact_daily_revenue "
            "WHERE region = ? GROUP BY order_date ORDER BY order_date"
        )
        tuning = tune_query(store, sql, ("Midwest",), "fact_daily_revenue", ["region", "order_date"])
    finally:
        store.close()

    # 3. Logical model: validate, then forward-engineer to both dialects.
    model = orders_model()
    issues = model.validate()
    pg_ddl = model.to_postgres_ddl()
    mysql_ddl = model.to_mysql_ddl()

    report = {
        "partitions_seeded": partitions,
        "first_run": {
            "status": first.status,
            "partitions_read": first.partitions_read,
            "rows_read": first.rows_read,
            "rows_loaded": first.rows_loaded,
            "rows_quarantined": first.rows_quarantined,
            "snapshot_id": first.snapshot_id,
        },
        "second_run": {
            "status": second.status,
            "partitions_read": second.partitions_read,
            "snapshot_id": second.snapshot_id,
        },
        "snapshots": len(list_snapshots(job.target_table_dir)),
        "silver_rows": len(silver),
        "gold_rows": len(gold),
        "gold_revenue": round(float(gold["total_revenue"].sum()), 2),
        "tuning": {
            "scanned_before": tuning.scanned_before,
            "uses_index_after": tuning.uses_index_after,
            "rows": tuning.rows,
        },
        "model_issues": issues,
        "postgres_ddl_tables": pg_ddl.count("CREATE TABLE"),
        "mysql_ddl_tables": mysql_ddl.count("CREATE TABLE"),
    }

    text = [
        "Glue-style ETL + relational tuning demo",
        "",
        render_job_report(first, list_snapshots(job.target_table_dir)),
        f"Second run (bookmark): {second.status}; partitions read: {len(second.partitions_read)}",
        f"Silver rows after both runs: {len(silver)}",
        f"Gold rows: {len(gold)}; total revenue: ${report['gold_revenue']:,.2f}",
        "",
        render_tuning_report(tuning),
        f"Logical model issues: {issues or '(none)'}",
        f"PostgreSQL DDL tables: {report['postgres_ddl_tables']}; Aurora MySQL DDL tables: {report['mysql_ddl_tables']}",
        "",
        "Honest limits: pandas + Parquet stand in for Glue/Iceberg/S3; SQLite stands in for",
        "PostgreSQL/Aurora. No AWS service, cluster or server is involved.",
    ]
    (root / "glue_relational_report.txt").write_text("\n".join(text) + "\n")
    (root / "glue_relational_report.json").write_text(json.dumps(report, indent=2))
    print("\n".join(text))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT)
    args = parser.parse_args()
    run_demo(args.out)


if __name__ == "__main__":
    main()
