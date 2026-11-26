"""CLI for the home-health pipeline: runs the full DAG and writes a
report (visit_report.json) plus a regenerated CATALOG.md."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from homehealth import pipeline, warehouse

BASE = Path(__file__).resolve().parent


def main() -> None:
    today = date(2026, 11, 26)
    conn = warehouse.connect(str(BASE / "home_health.db"))
    report = pipeline.run(
        conn,
        str(BASE / "data" / "visits.csv"),
        str(BASE / "data" / "referrals.json"),
        run_id="demo-2026-11-26",
        today=today,
        incremental=False,
    )
    with open(BASE / "visit_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    catalog = ["# Home Health Warehouse Catalog", ""]
    catalog.append("Generated from the warehouse that actually ran.")
    catalog.append("")
    catalog.append("## Visits by date")
    catalog.append("")
    catalog.append("| visit_date | visits | total_minutes | avg_assessment_score |")
    catalog.append("|---|---|---|---|")
    for row in report["summary"]:
        catalog.append(
            f"| {row['visit_date']} | {row['visits']} | "
            f"{row['total_minutes']} | {row['avg_assessment_score']} |"
        )
    catalog.append("")
    with open(BASE / "CATALOG.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(catalog))
    print(
        f"run {report['run_id']}: {report['source_rows']} source rows, "
        f"{report['loaded']} loaded, {report['quarantined']} quarantined, "
        f"{report['referrals']} referrals, "
        f"{report['api_retries']} API retries, "
        f"reconciled={report['reconciled']}"
    )


if __name__ == "__main__":
    main()
