"""Run the governed lakehouse checks and write governance_report.txt.

Usage:  python run_governance.py
Builds bronze -> silver -> gold, decides the seeded access requests against
the grants, reconciles gold back to silver, and rebuilds gold as of
2026-06-30 to show point-in-time history.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.governance import run_governance

BASE = Path(__file__).parent


def main() -> None:
    summary = run_governance()
    rec = summary["reconciliation"]
    decisions = summary["decisions"]
    lines = [
        "GOVERNED LAKEHOUSE — ACCESS, RECONCILIATION & POINT-IN-TIME REPORT",
        f"Bronze orders: {summary['bronze_orders']} rows",
        f"Silver orders: {summary['silver_rows']} rows "
        f"({summary['quarantined_rows']} quarantined)",
        f"Gold daily groups: {summary['gold_groups']}, "
        f"revenue ${summary['gold_revenue']:,.2f}",
        "",
        "ACCESS CONTROL",
        f"Grants: {summary['grants']}; requests decided: {summary['requests']} "
        f"({summary['allowed']} allowed, {summary['denied']} denied)",
        f"Audit log entries: {summary['audit_entries']} (one per request)",
    ]
    for row in decisions.to_dict("records"):
        lines.append(
            f"  {row['request_id']} {row['role']} -> {row['table']} "
            f"({row['purpose']}): {row['decision']} — {row['reason']}"
        )
    lines += [
        "",
        "RECONCILIATION",
        f"Silver revenue ${rec['silver_revenue']:,.2f} vs "
        f"gold revenue ${rec['gold_revenue']:,.2f} "
        f"(difference ${rec['difference']:.2f}) over {rec['gold_groups']} groups",
        f"Reconciled: {'YES' if rec['reconciled'] else 'NO'}",
        "",
        "POINT-IN-TIME HISTORY",
        f"Gold as of {summary['point_in_time_date']}: "
        f"{summary['point_in_time_groups']} groups, "
        f"revenue ${summary['point_in_time_revenue']:,.2f}",
        f"Point-in-time reconciled: "
        f"{'YES' if summary['point_in_time_reconciled'] else 'NO'}",
    ]
    (BASE / "governance_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
