#!/usr/bin/env python3
"""Run the inbound attack detection pipeline end to end.

Generates the seeded synthetic dataset, scores every message, stores
results in detection_results.db, writes detection_report.json, and
prints a readable summary.
"""

from __future__ import annotations

from pathlib import Path

from detection.pipeline import format_report, run_pipeline

BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    report = run_pipeline(
        seed=42,
        db_path=BASE_DIR / "detection_results.db",
        report_path=BASE_DIR / "detection_report.json",
    )
    print(format_report(report))
    print(f"\nWrote {BASE_DIR / 'detection_report.json'}")
    print(f"Wrote {BASE_DIR / 'detection_results.db'}")


if __name__ == "__main__":
    main()
