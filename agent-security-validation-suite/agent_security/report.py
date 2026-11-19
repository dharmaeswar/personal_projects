"""Plain-text and JSON reports for the eval suites."""
import json


def render_text(guardrail_rows, guardrail_summary, mcp_rows, monitor_anomalies):
    lines = ["AGENT SECURITY VALIDATION SUITE", "=" * 34, ""]
    lines.append("Guardrail evals: %d/%d passed (pass rate %.1f%%)" % (
        guardrail_summary["passed"], guardrail_summary["total"],
        guardrail_summary["pass_rate"] * 100))
    lines.append("Bypass rate (attacks that got through): %.1f%%" % (
        guardrail_summary["bypass_rate"] * 100))
    lines.append("False positive rate (benign blocked): %.1f%%" % (
        guardrail_summary["false_positive_rate"] * 100))
    if guardrail_summary["bypassed_cases"]:
        lines.append("BYPASSED: " + ", ".join(guardrail_summary["bypassed_cases"]))
    if guardrail_summary["false_positives"]:
        lines.append("FALSE POSITIVES: " +
                     ", ".join(guardrail_summary["false_positives"]))
    lines.append("")
    lines.append("Per category:")
    for cat, vals in sorted(guardrail_summary["by_category"].items()):
        lines.append("  %-18s %d/%d passed" % (cat, vals["passed"], vals["total"]))
    lines.append("")
    mcp_passed = sum(1 for r in mcp_rows if r["passed"])
    lines.append("MCP authorization scenarios: %d/%d passed" %
                 (mcp_passed, len(mcp_rows)))
    for r in mcp_rows:
        if not r["passed"]:
            lines.append("  FAIL %s scopes=%s: %s" %
                         (r["tool"], ",".join(r["scopes"]), r["reason"]))
    lines.append("")
    lines.append("Session monitor anomalies in demo session: %d" %
                 len(monitor_anomalies))
    for a in monitor_anomalies:
        lines.append("  [%s] %s: %s" % (a.severity, a.kind, a.detail))
    return "\n".join(lines) + "\n"


def render_json(guardrail_rows, guardrail_summary, mcp_rows, monitor_anomalies):
    return json.dumps({
        "guardrail_summary": guardrail_summary,
        "guardrail_rows": guardrail_rows,
        "mcp_rows": mcp_rows,
        "monitor_anomalies": [
            {"kind": a.kind, "detail": a.detail, "severity": a.severity}
            for a in monitor_anomalies],
    }, indent=2)
