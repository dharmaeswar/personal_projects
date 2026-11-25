"""Incident triage: severity, runbook mapping, escalation, SLA timers.

Synthetic incident records only. Severity follows impact plus
urgency; each severity maps to a runbook, an escalation target and
an SLA in minutes. No real incident system is contacted.
"""

RUNBOOKS = {
    "stale-feed": "RUNBOOK.md#stale-market-data-feed",
    "stuck-orders": "RUNBOOK.md#stuck-orders",
    "latency-breach": "RUNBOOK.md#latency-breach",
    "reject-spike": "RUNBOOK.md#reject-spike",
    "unknown": "RUNBOOK.md#general-triage",
}

SLA_MINUTES = {"sev1": 15, "sev2": 60, "sev3": 240, "sev4": 1440}
ESCALATE_TO = {
    "sev1": "trading desk head + platform on-call",
    "sev2": "platform on-call",
    "sev3": "ops duty manager",
    "sev4": "ops queue",
}


def classify_severity(impact, urgency):
    """impact/urgency are 'high', 'medium' or 'low'."""
    if impact == "high" and urgency == "high":
        return "sev1"
    if impact == "high" or urgency == "high":
        return "sev2"
    if impact == "medium" or urgency == "medium":
        return "sev3"
    return "sev4"


def triage(incident):
    """Triage one incident dict with ``kind``, ``impact``, ``urgency``.

    Returns severity, runbook link, escalation target and SLA minutes.
    """
    severity = classify_severity(incident["impact"], incident["urgency"])
    return {
        "id": incident.get("id", "unknown"),
        "kind": incident["kind"],
        "severity": severity,
        "runbook": RUNBOOKS.get(incident["kind"], RUNBOOKS["unknown"]),
        "escalate_to": ESCALATE_TO[severity],
        "sla_minutes": SLA_MINUTES[severity],
    }
