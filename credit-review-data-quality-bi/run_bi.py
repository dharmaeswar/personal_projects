#!/usr/bin/env python3
"""Run the Credit Review data-quality checks and BI dashboard.

Usage:
    python run_bi.py [--out DIR]

Writes dashboard_report.txt and dashboard_metrics.csv into the output
directory (default: the project root). Exits non-zero when any data
quality check fails, so it can sit behind a scheduled job or CI gate.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from credit_review_bi import build_dataset, run_quality_checks, build_dashboard
from credit_review_bi.metrics import format_dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=".", help="output directory")
    args = parser.parse_args()

    dataset = build_dataset()
    checks = run_quality_checks(dataset)
    dashboard = build_dashboard(dataset, checks)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dashboard_report.txt").write_text(format_dashboard(dashboard))

    with open(out / "dashboard_metrics.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerow(["loan_count", dashboard["portfolio"]["loan_count"]])
        writer.writerow(["total_outstanding_usd",
                         dashboard["portfolio"]["total_outstanding_usd"]])
        writer.writerow(["review_count", dashboard["reviews"]["review_count"]])
        writer.writerow(["median_cycle_days", dashboard["reviews"]["median_cycle_days"]])
        writer.writerow(["overdue_reviews", dashboard["reviews"]["overdue_reviews"]])
        writer.writerow(["open_findings", dashboard["findings"]["open_findings"]])
        writer.writerow(["overdue_findings", dashboard["findings"]["overdue_findings"]])
        writer.writerow(["data_quality_score", dashboard["data_quality"]["score"]])

    print(format_dashboard(dashboard))
    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"{len(failed)} data-quality check(s) FAILED:")
        for check in failed:
            print(f"  - {check.name}: {check.detail} (rows: {check.failed_ids})")
        return 1
    print("All data-quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
