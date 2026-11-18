"""Human-readable validation report written next to the pipeline tables."""
from pathlib import Path


def render_report(summary, checks, invalid):
    lines = [
        "PySpark Pipeline Validation — run report",
        f"Raw rows: {summary['raw_rows']}",
        f"Duplicates removed (window dedup): {summary['duplicates_removed']}",
        f"Quarantined rows: {summary['quarantined_rows']}",
        f"Cleansed rows: {summary['cleansed_rows']}",
        f"Gold aggregate rows: {summary['gold_rows']}",
        f"Curated partitions (by event_date): {summary['partitions']}",
        f"Total cleansed revenue: ${summary['total_revenue']:,.2f}",
        f"Reconciliation gold vs cleansed: {'PASS' if summary['reconciliation_passed'] else 'FAIL'}",
        "",
        "Violations quarantined:",
    ]
    for rule, count in sorted(summary["violation_counts"].items()):
        lines.append(f"  {rule}: {count}")
    lines += ["", "Quality checks:"]
    for name, status, detail in checks:
        lines.append(f"  [{status}] {name}: {detail}")
    lines += ["", "Quarantined event_ids:"]
    for event_id, violation in zip(invalid["event_id"], invalid["violation"]):
        lines.append(f"  {event_id}: {violation}")
    return "\n".join(lines) + "\n"
