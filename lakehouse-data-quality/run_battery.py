"""Run the battery-telemetry pipeline and write battery_report.txt.

Usage:  python run_battery.py
Tables land in lakehouse_tables/battery/ (bronze, silver, gold). The run
is deterministic: the same seed produces the same telemetry, the same
13 quarantined rows and the same gold aggregates on every run.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.battery import run_battery_telemetry

BASE = Path(__file__).parent
BATTERY_DIR = BASE / "lakehouse_tables" / "battery"


def main() -> None:
    summary = run_battery_telemetry(BATTERY_DIR)
    rec = summary["reconciliation"]
    lines = [
        "Battery telemetry (cell-cycling time-series -> medallion lakehouse)",
        f"Bronze telemetry: {summary['bronze_rows']} samples",
        f"Silver telemetry: {summary['silver_rows']} samples",
        f"Quarantined rows: {summary['quarantine_rows']}",
        f"Gold daily groups: {summary['gold_groups']}",
        "",
        "BRONZE CHECKS",
    ]
    for result in summary["checks"]:
        lines.append(str(result))
    lines += [
        "",
        "RECONCILIATION",
        str(rec),
        "",
        "SCHEMA",
        f"Silver schema violations: {len(summary['silver_schema_violations'])}",
        f"Gold schema violations: {len(summary['gold_schema_violations'])}",
        "",
        "SUMMARY",
        f"{summary['checks_failed']} of {len(summary['checks'])} bronze checks "
        f"FAILED; {summary['quarantine_rows']} bad rows quarantined, none dropped silently.",
        "Reconciliation: "
        + ("gold matches silver." if rec.passed else "MISMATCH — see above."),
        "Delta log versions: "
        + ", ".join(f"{k} v{v}" for k, v in summary["log_versions"].items()),
    ]
    report = "\n".join(lines) + "\n"
    (BASE / "battery_report.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
