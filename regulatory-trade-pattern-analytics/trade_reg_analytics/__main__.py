"""Run the full regulatory analytics pipeline.

Builds the SQLite warehouse from seeded synthetic data, runs the
statistical triage and all pattern detectors, and writes the
regulatory report artefacts.

Usage:
    python -m trade_reg_analytics --db warehouse.db --out report
"""

from __future__ import annotations

import argparse

from .data import WarehouseConfig, build_warehouse, load_table
from .patterns import run_all_detectors
from .report import findings_summary, write_report
from .stats import daily_volume
from .tuning import run_tuning


def main() -> None:
    parser = argparse.ArgumentParser(description="Regulatory trade-pattern analytics")
    parser.add_argument("--db", default="warehouse.db", help="SQLite warehouse path")
    parser.add_argument("--out", default="report", help="Report output directory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--tune", action="store_true",
                        help="Tune the analytics queries and write a tuning report")
    args = parser.parse_args()

    cfg = WarehouseConfig(seed=args.seed, days=args.days)
    counts = build_warehouse(args.db, cfg)
    print(f"Warehouse built: {counts}")

    orders = load_table(args.db, "orders")
    trades = load_table(args.db, "trades")
    positions = load_table(args.db, "positions")
    daily = daily_volume(trades)
    findings = run_all_detectors(orders, trades, positions)
    summary = findings_summary(findings)
    print(f"Findings: {summary['total_findings']} (top severity {summary['top_severity']})")
    for pattern, info in summary["by_pattern"].items():
        print(f"  {pattern}: {info['count']} findings, max severity {info['max_severity']}")
    files = write_report(findings, daily, args.out)
    for name, path in files.items():
        print(f"  {name}: {path}")
    if args.tune:
        import sqlite3

        conn = sqlite3.connect(args.db)
        try:
            tuning = run_tuning(conn, args.out)
        finally:
            conn.close()
        print(f"Tuning: {tuning['queries_tuned']} queries, "
              f"{tuning['full_scans_removed']} full scans removed")
        for r in tuning["results"]:
            print(f"  {r['name']}: {r['median_ms_before']} ms -> "
                  f"{r['median_ms_after']} ms ({r['speedup']}x)")


if __name__ == "__main__":
    main()
