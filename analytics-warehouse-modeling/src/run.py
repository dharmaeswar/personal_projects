"""End-to-end warehouse run: load -> checks -> analytics -> report.

Usage (from the project root):
    python -m src.run [--db output/warehouse.db] [--run-date 2026-11-13]

The run is idempotent: re-running the same sample feeds inserts
0 new facts. The report is printed and saved as JSON to
output/run_report.json; analytics results go to output/analytics.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analytics import run_analytics  # noqa: E402
from src.loader import load_reference_data, load_usage_events  # noqa: E402
from src.model import init_warehouse  # noqa: E402
from src.quality import SLA_DAYS, run_all_checks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path):
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the analytics warehouse load")
    parser.add_argument("--db", default="output/warehouse.db")
    parser.add_argument("--run-date", default=date.today().isoformat(),
                        help="Run date YYYY-MM-DD (used for the SLA check)")
    parser.add_argument("--batch-id", default=None,
                        help="Load batch id (default: run-date)")
    args = parser.parse_args()

    batch_id = args.batch_id or f"batch-{args.run_date}"
    db_path = ROOT / args.db if not Path(args.db).is_absolute() else Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "output").mkdir(exist_ok=True)

    accounts = _load_json(ROOT / "data" / "sample_accounts.json")
    regions = _load_json(ROOT / "data" / "sample_regions.json")
    events = _load_json(ROOT / "data" / "sample_events.json")

    conn = init_warehouse(str(db_path))
    ref_summary, ref_quarantined = load_reference_data(conn, accounts, regions)
    load_summary, event_quarantined = load_usage_events(conn, events, batch_id)
    quarantined = ref_quarantined + event_quarantined
    checks = run_all_checks(conn, run_date=args.run_date)
    analytics = run_analytics(conn)

    sla = next(c for c in checks if c["name"] == "freshness_sla")
    report = {
        "batch_id": batch_id,
        "run_date": args.run_date,
        "sla_days": SLA_DAYS,
        "sla_status": "PASS" if sla["passed"] else "FAIL",
        "reference_data": ref_summary,
        "load": load_summary,
        "rows_loaded": load_summary["facts_inserted"],
        "rows_quarantined": len(quarantined),
        "quarantined": quarantined,
        "checks": checks,
        "all_checks_passed": all(c["passed"] for c in checks),
        "analytics_row_counts": {k: len(v) for k, v in analytics.items()},
    }
    (ROOT / "output" / "run_report.json").write_text(json.dumps(report, indent=2))
    (ROOT / "output" / "analytics.json").write_text(json.dumps(analytics, indent=2))

    print(f"Batch: {batch_id}  Run date: {args.run_date}")
    print(f"Facts inserted: {report['rows_loaded']}  "
          f"Skipped duplicates: {load_summary['skipped_duplicates']}  "
          f"Quarantined: {report['rows_quarantined']}")
    print(f"SLA ({SLA_DAYS} days): {report['sla_status']} — {sla['details']}")
    for check in checks:
        print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {check['name']}: {check['details']}")
    print(f"Analytics rows: {report['analytics_row_counts']}")
    print("Report: output/run_report.json  Analytics: output/analytics.json")
    conn.close()
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
