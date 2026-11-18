"""Render a quality report as text and JSON."""

import json


def render_text(report):
    summary = report["summary"]
    lines = [
        "AI EVALUATION DATA QUALITY REPORT",
        "=" * 40,
        "Records checked: %d" % summary["total_records"],
        "Findings: %d (%d critical, %d warnings)"
        % (summary["total_findings"], summary["critical"],
           summary["warnings"]),
        "Quality gate: %s" % summary["gate"],
        "",
        "Findings by check:",
    ]
    for check, count in sorted(summary["findings_by_check"].items()):
        lines.append("  - %s: %d" % (check, count))
    lines.append("")
    lines.append("Coverage (eval split, records per category):")
    for label, count in sorted(report["coverage"].items()):
        lines.append("  - %s: %d" % (label, count))
    lines.append("")
    lines.append("Findings:")
    if not report["findings"]:
        lines.append("  (none)")
    for finding in report["findings"]:
        lines.append("  [%s] %s | %s | %s"
                     % (finding["severity"], finding["check"],
                        finding["record_id"], finding["detail"]))
    return "\n".join(lines) + "\n"


def render_json(report):
    return json.dumps(report, indent=2) + "\n"
