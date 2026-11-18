"""Run the lakehouse pipeline as an orchestrated DAG.

Usage: python run_orchestrated.py [--run-id ID]
Runs ingest -> validate -> silver -> gold -> reconcile/report as DAG
tasks (see lakehouse/orchestration.py), snapshots the silver and gold
tables after each build (see lakehouse/snapshots.py), and writes
orchestration_report.txt in the project root. Re-running with the same
--run-id resumes: tasks that already succeeded with the same inputs
are skipped instead of re-run. Each task reads its inputs from the
lakehouse tables on disk, so a resumed run works from persisted state.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lakehouse.checks import check_reconciliation, run_all_checks
from lakehouse.data import generate_bronze
from lakehouse.orchestration import DagRunner, Task, render_run_report
from lakehouse.pipeline import (
    build_gold,
    build_silver,
    read_log,
    read_table,
    write_table,
)
from lakehouse.report import render_report
from lakehouse.snapshots import commit_snapshot


def build_tasks(root: Path, out: Path) -> list[Task]:
    def ingest(context: dict) -> None:
        bronze = generate_bronze()
        for name, df in bronze.items():
            entry = write_table(df, out / "bronze" / name, f"bronze ingest ({name})")
            print(f"bronze/{name}: {len(df)} rows (log v{entry['version']})")

    def validate(context: dict) -> None:
        orders = read_table(out / "bronze" / "orders")
        customers = read_table(out / "bronze" / "customers")
        products = read_table(out / "bronze" / "products")
        results = run_all_checks(orders, customers, products)
        failed = [r for r in results if not r.passed]
        print(f"bronze checks: {len(results) - len(failed)}/{len(results)} passed")

    def silver(context: dict) -> None:
        orders = read_table(out / "bronze" / "orders")
        customers = read_table(out / "bronze" / "customers")
        products = read_table(out / "bronze" / "products")
        silver, quarantine = build_silver(orders, customers, products)
        write_table(silver, out / "silver" / "orders", "silver clean")
        write_table(quarantine, out / "silver" / "quarantine", "silver quarantine")
        entry = commit_snapshot(silver, out / "snapshots" / "silver_orders", "silver clean")
        print(f"silver/orders: {len(silver)} rows, quarantined {len(quarantine)} (snapshot {entry['snapshot_id']})")

    def gold(context: dict) -> None:
        silver = read_table(out / "silver" / "orders")
        products = read_table(out / "bronze" / "products")
        gold = build_gold(silver, products)
        write_table(gold, out / "gold" / "daily_revenue", "gold aggregate")
        entry = commit_snapshot(gold, out / "snapshots" / "daily_revenue", "gold aggregate")
        print(f"gold/daily_revenue: {len(gold)} groups (snapshot {entry['snapshot_id']})")

    def reconcile(context: dict) -> None:
        orders = read_table(out / "bronze" / "orders")
        customers = read_table(out / "bronze" / "customers")
        products = read_table(out / "bronze" / "products")
        silver = read_table(out / "silver" / "orders")
        quarantine = read_table(out / "silver" / "quarantine")
        gold = read_table(out / "gold" / "daily_revenue")
        results = run_all_checks(orders, customers, products)
        reconciliation = check_reconciliation(silver, products, gold)
        report = render_report(
            results,
            bronze_rows=len(orders),
            silver_rows=len(silver),
            quarantine_rows=len(quarantine),
            gold_groups=len(gold),
            reconciliation=reconciliation,
        )
        (root / "validation_report.txt").write_text(report)
        print(report)
        print("Delta log versions:", {t: len(read_log(out / t)) for t in ("bronze/orders", "silver/orders", "gold/daily_revenue")})

    return [
        Task("ingest_bronze", ingest),
        Task("validate_bronze", validate, depends_on=["ingest_bronze"]),
        Task("build_silver", silver, depends_on=["validate_bronze"], max_retries=2),
        Task("build_gold", gold, depends_on=["build_silver"], max_retries=2),
        Task("reconcile_report", reconcile, depends_on=["build_gold"]),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="daily")
    parser.add_argument("--out", default="lakehouse_tables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    runner = DagRunner(build_tasks(root, out), out / "orchestration_state.json")
    context: dict = {"inputs": {name: {"source": "seed-42"} for name in (
        "ingest_bronze", "validate_bronze", "build_silver", "build_gold", "reconcile_report")}}
    result = runner.run(context, run_id=args.run_id)
    report = render_run_report(result)
    (root / "orchestration_report.txt").write_text(report)
    print()
    print(report)
    raise SystemExit(0 if result.succeeded else 1)


if __name__ == "__main__":
    main()
