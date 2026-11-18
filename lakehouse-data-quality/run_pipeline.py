"""Run the full lakehouse pipeline and write the validation report.

Usage: python run_pipeline.py [--out DIR]
Writes Parquet tables to <out>/bronze, <out>/silver, <out>/gold and a
validation_report.txt in the project root.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lakehouse.checks import check_reconciliation, run_all_checks
from lakehouse.data import generate_bronze
from lakehouse.pipeline import build_gold, build_silver, read_log, write_table
from lakehouse.report import render_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="lakehouse_tables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    bronze = generate_bronze()
    for name, df in bronze.items():
        entry = write_table(df, out / "bronze" / name, f"bronze ingest ({name})")
        print(f"bronze/{name}: {len(df)} rows (log v{entry['version']})")

    results = run_all_checks(bronze["orders"], bronze["customers"], bronze["products"])
    silver, quarantine = build_silver(
        bronze["orders"], bronze["customers"], bronze["products"]
    )
    entry = write_table(silver, out / "silver" / "orders", "silver clean")
    print(f"silver/orders: {len(silver)} rows (log v{entry['version']})")
    entry = write_table(
        quarantine, out / "silver" / "quarantine", "silver quarantine"
    )
    print(f"silver/quarantine: {len(quarantine)} rows (log v{entry['version']})")

    gold = build_gold(silver, bronze["products"])
    entry = write_table(gold, out / "gold" / "daily_revenue", "gold aggregate")
    print(f"gold/daily_revenue: {len(gold)} groups (log v{entry['version']})")

    reconciliation = check_reconciliation(silver, bronze["products"], gold)
    report = render_report(
        results,
        bronze_rows=len(bronze["orders"]),
        silver_rows=len(silver),
        quarantine_rows=len(quarantine),
        gold_groups=len(gold),
        reconciliation=reconciliation,
    )
    (root / "validation_report.txt").write_text(report)
    print()
    print(report)
    print("Delta log versions:", {t: len(read_log(out / t)) for t in ("bronze/orders", "silver/orders", "gold/daily_revenue")})


if __name__ == "__main__":
    main()
