"""Evidence collection: one evidence record per control.

Each control states what was checked, the counts behind the verdict,
and a pass/fail against a stated threshold. The controls are
illustrative examples of the kind of control a security-analytics
pipeline would measure; they are not an audit opinion and the data is
synthetic. KPIs here are structured so they could map to common
control frameworks, but no framework expertise is claimed.
"""

from __future__ import annotations

CONTROLS = [
    {
        "control_id": "CTRL-01",
        "name": "Privileged access requires MFA",
        "threshold": "100% of privileged identities have MFA enabled",
    },
    {
        "control_id": "CTRL-02",
        "name": "Dormant privileged access is reviewed",
        "threshold": "0 privileged identities dormant over 90 days",
    },
    {
        "control_id": "CTRL-03",
        "name": "Findings are remediated by their due date",
        "threshold": "0 open findings past due",
    },
    {
        "control_id": "CTRL-04",
        "name": "Login anomalies are detected",
        "threshold": "0 undetected impossible-travel logins and brute-force bursts",
    },
    {
        "control_id": "CTRL-05",
        "name": "Security telemetry is complete and referentially valid",
        "threshold": "0 quarantined rows out of staged rows",
    },
]


def build_evidence(kpis: dict, anomalies: dict, checks) -> list[dict]:
    passed_checks = sum(1 for c in checks if c.passed)
    staged_rows = kpis["staged_rows"]
    evidence = [
        {
            "control_id": "CTRL-01",
            "name": CONTROLS[0]["name"],
            "checked": (
                f"{kpis['privileged_with_mfa']} of {kpis['privileged_identities']} "
                f"privileged identities have MFA enabled"
            ),
            "value": f"{kpis['mfa_coverage_privileged_pct']}%",
            "threshold": CONTROLS[0]["threshold"],
            "passed": kpis["mfa_coverage_privileged_pct"] == 100.0,
        },
        {
            "control_id": "CTRL-02",
            "name": CONTROLS[1]["name"],
            "checked": (
                f"{kpis['dormant_privileged']} of {kpis['privileged_identities']} "
                f"privileged identities dormant over 90 days"
            ),
            "value": str(kpis["dormant_privileged"]),
            "threshold": CONTROLS[1]["threshold"],
            "passed": kpis["dormant_privileged"] == 0,
        },
        {
            "control_id": "CTRL-03",
            "name": CONTROLS[2]["name"],
            "checked": (
                f"{kpis['overdue_findings']} of {kpis['open_findings']} open "
                f"findings past due; mean time to remediate "
                f"{kpis['mttr_days']} days over {kpis['remediated_findings']} "
                f"remediated findings"
            ),
            "value": str(kpis["overdue_findings"]),
            "threshold": CONTROLS[2]["threshold"],
            "passed": kpis["overdue_findings"] == 0,
        },
        {
            "control_id": "CTRL-04",
            "name": CONTROLS[3]["name"],
            "checked": (
                f"{len(anomalies['impossible_travel'])} impossible-travel "
                f"login pair(s), {len(anomalies['brute_force'])} brute-force "
                f"burst(s) detected in {kpis['successful_logins']} successful "
                f"logins"
            ),
            "value": str(
                len(anomalies["impossible_travel"]) + len(anomalies["brute_force"])
            ),
            "threshold": CONTROLS[3]["threshold"],
            "passed": not anomalies["impossible_travel"]
            and not anomalies["brute_force"],
        },
        {
            "control_id": "CTRL-05",
            "name": CONTROLS[4]["name"],
            "checked": (
                f"{kpis['quarantined_rows']} of {staged_rows} staged rows "
                f"quarantined; {passed_checks} of {len(checks)} data-quality "
                f"checks passed"
            ),
            "value": str(kpis["quarantined_rows"]),
            "threshold": CONTROLS[4]["threshold"],
            "passed": kpis["quarantined_rows"] == 0,
        },
    ]
    return evidence


def evidence_completeness(evidence: list[dict]) -> float:
    """Share of controls with evidence collected (all controls always
    have evidence in this pipeline, so this is 100% by construction;
    it is reported so a missing control would show up)."""
    if not evidence:
        return 0.0
    collected = sum(1 for e in evidence if e.get("checked"))
    return round(100.0 * collected / len(evidence), 1)
