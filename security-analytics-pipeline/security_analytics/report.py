"""Render the human-readable validation report."""

from __future__ import annotations


def render_report(
    *,
    checks,
    counts: dict,
    kpis: dict,
    anomalies: dict,
    evidence: list[dict],
    evidence_pct: float,
) -> str:
    lines = [
        "Security Analytics Pipeline — Validation Report",
        "=================================================",
        "",
        "Pipeline stages",
        "---------------",
        f"Staged login events:  {counts['raw_login_events']}",
        f"Staged audit events:  {counts['raw_audit_events']}",
        f"Staged findings:      {counts['raw_findings']}",
        f"Identities:           {counts['identities']}",
        f"Assets:               {counts['assets']}",
        f"Normalized events:    {counts['events']}",
        f"Normalized findings:  {counts['findings']}",
        f"Quarantined rows:     {counts['quarantine']}",
        f"Late-arriving events: {kpis['late_events']} (normalized, flagged)",
        "",
        "Data-quality checks",
        "-------------------",
    ]
    for check in checks:
        lines.append(str(check))
    passed = sum(1 for c in checks if c.passed)
    lines.append(f"Checks: {passed} of {len(checks)} passed")
    lines += [
        "",
        "Control-effectiveness KPIs",
        "--------------------------",
        f"MFA coverage (privileged): {kpis['mfa_coverage_privileged_pct']}% "
        f"({kpis['privileged_with_mfa']}/{kpis['privileged_identities']})",
        f"MFA coverage (all identities): {kpis['mfa_coverage_all_pct']}%",
        f"Successful logins with MFA: {kpis['mfa_login_usage_pct']}% "
        f"({kpis['successful_logins_with_mfa']}/{kpis['successful_logins']})",
        f"Stale privileged access: {kpis['stale_access_pct']}% "
        f"({kpis['dormant_privileged']}/{kpis['privileged_identities']} dormant > 90 days)",
        f"Mean time to remediate findings: {kpis['mttr_days']} days "
        f"({kpis['remediated_findings']} remediated)",
        f"Overdue findings: {kpis['overdue_findings']} of {kpis['total_findings']} "
        f"({kpis['overdue_findings_pct']}%), {kpis['open_findings']} still open",
        f"Findings by severity: {kpis['findings_by_severity']}",
        f"Open findings by severity: {kpis['open_findings_by_severity']}",
        "",
        "Anomalies flagged",
        "-----------------",
        f"Impossible-travel logins: {len(anomalies['impossible_travel'])}",
    ]
    for a in anomalies["impossible_travel"]:
        lines.append(
            f"  - {a['identity_id']}: {a['first_city']} ({a['first_country']}) -> "
            f"{a['second_city']} ({a['second_country']}) in {a['gap_minutes']} min"
        )
    lines.append(f"Dormant privileged accounts: {len(anomalies['dormant_privileged'])}")
    for a in anomalies["dormant_privileged"]:
        lines.append(
            f"  - {a['identity_id']} ({a['name']}): last login "
            f"{a['last_login_days_ago']} days ago"
        )
    lines.append(f"Overdue findings: {len(anomalies['overdue_findings'])}")
    for a in anomalies["overdue_findings"]:
        lines.append(
            f"  - {a['finding_id']} [{a['severity']}] on {a['asset_id']}: "
            f"{a['title']} (due {a['due_date'][:10]})"
        )
    lines.append(f"Brute-force bursts: {len(anomalies['brute_force'])}")
    for a in anomalies["brute_force"]:
        lines.append(
            f"  - {a['identity_id']}: {a['failed_logins']} failed logins from "
            f"{a['ip']} between {a['first_ts']} and {a['last_ts']}"
        )
    lines += [
        "",
        "Evidence collection per control",
        "-------------------------------",
        f"Evidence completeness: {evidence_pct}% "
        f"({len(evidence)} of {len(evidence)} controls have evidence)",
    ]
    for e in evidence:
        status = "PASS" if e["passed"] else "FAIL"
        lines.append(
            f"{e['control_id']} [{status}] {e['name']}\n"
            f"    checked: {e['checked']}\n"
            f"    value: {e['value']} | threshold: {e['threshold']}"
        )
    lines += [
        "",
        "Notes",
        "-----",
        "All data is synthetic and seeded; nothing here describes a real",
        "organization or a real security posture. The controls are",
        "illustrative examples, not an audit opinion.",
    ]
    return "\n".join(lines) + "\n"
