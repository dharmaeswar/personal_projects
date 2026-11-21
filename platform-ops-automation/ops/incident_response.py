"""Incident response: on-call rotation, incident lifecycle, SLA tracking,
and ServiceNow-style ticket sync for the Platform Ops Automation demo.

The M&T SRE role this module supports is enterprise platform support:
someone has to be on call, incidents have to move through a lifecycle
with SLA timers, and every incident has a ticket that stays in sync.
All data is synthetic and local; nothing here claims production
ServiceNow or Azure experience.

Incident states: detected -> triaged -> mitigating -> resolved -> closed.
SLA targets (minutes) by severity:
    Sev1: acknowledge 15, resolve 240
    Sev2: acknowledge 60, resolve 1440
    Sev3: acknowledge 480, resolve 4320
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SEVERITIES = ("Sev1", "Sev2", "Sev3")
SLA_MINUTES = {
    "Sev1": {"acknowledge": 15, "resolve": 240},
    "Sev2": {"acknowledge": 60, "resolve": 1440},
    "Sev3": {"acknowledge": 480, "resolve": 4320},
}
TRANSITIONS = {
    "detected": ("triaged",),
    "triaged": ("mitigating", "resolved"),
    "mitigating": ("resolved",),
    "resolved": ("closed",),
    "closed": (),
}
RUNBOOKS = {
    "high-error-rate": ["Check the error breakdown by endpoint in the logs.",
                        "Roll back the last deploy if errors started with it.",
                        "Scale the service if the errors are capacity-driven."],
    "latency-spike": ["Check downstream dependency latency first.",
                      "Look for a hot partition or a slow query.",
                      "Shed non-critical traffic if the SLO is at risk."],
    "pod-crashes": ["Read the crash loop logs for the failing container.",
                    "Check memory limits against actual usage.",
                    "Roll back the image if the crash started with a release."],
}


def on_call(roster: list[str], start: datetime, at: datetime,
            rotation_days: int = 7) -> dict:
    """Who is on call at ``at`` for a weekly rotation starting ``start``.

    Returns {"primary": name, "secondary": name}. Raises ValueError for
    an empty roster or a date before the rotation starts.
    """
    if not roster:
        raise ValueError("On-call roster is empty")
    if at < start:
        raise ValueError("Date is before the rotation start")
    index = ((at - start).days // rotation_days) % len(roster)
    return {
        "primary": roster[index],
        "secondary": roster[(index + 1) % len(roster)],
    }


class Incident:
    """One incident, from detection through closure."""

    def __init__(self, incident_id: str, title: str, severity: str,
                 service: str, detected_at: datetime,
                 runbook: str = "high-error-rate") -> None:
        if severity not in SEVERITIES:
            raise ValueError(f"Unknown severity: {severity!r}. Choose from {SEVERITIES}")
        if runbook not in RUNBOOKS:
            raise ValueError(f"Unknown runbook: {runbook!r}. Choose from {sorted(RUNBOOKS)}")
        self.incident_id = incident_id
        self.title = title
        self.severity = severity
        self.service = service
        self.detected_at = detected_at
        self.runbook = runbook
        self.state = "detected"
        self.acknowledged_at: datetime | None = None
        self.resolved_at: datetime | None = None
        self.closed_at: datetime | None = None
        self.history: list[dict] = [self._event("detected", detected_at, "system")]

    def _event(self, state: str, at: datetime, actor: str) -> dict:
        return {"state": state, "at": at, "actor": actor}

    def transition(self, new_state: str, at: datetime, actor: str) -> None:
        """Move to a new state. Raises ValueError on an invalid transition."""
        if new_state not in TRANSITIONS[self.state]:
            raise ValueError(
                f"Cannot move incident {self.incident_id} from {self.state} "
                f"to {new_state}; allowed: {TRANSITIONS[self.state] or 'none'}")
        if at < self.detected_at:
            raise ValueError("Transition time is before the incident was detected")
        self.state = new_state
        if new_state == "triaged":
            self.acknowledged_at = at
        if new_state == "resolved":
            self.resolved_at = at
        if new_state == "closed":
            self.closed_at = at
        self.history.append(self._event(new_state, at, actor))

    def sla_status(self, at: datetime | None = None) -> dict:
        """SLA standing: acknowledge and resolve targets, breached or met."""
        at = at or datetime.now(timezone.utc)
        targets = SLA_MINUTES[self.severity]
        ack_deadline = self.detected_at + timedelta(minutes=targets["acknowledge"])
        resolve_deadline = self.detected_at + timedelta(minutes=targets["resolve"])
        acked = self.acknowledged_at is not None
        resolved = self.resolved_at is not None
        return {
            "acknowledge_deadline": ack_deadline,
            "resolve_deadline": resolve_deadline,
            "acknowledged": acked,
            "acknowledge_breached": (not acked and at > ack_deadline)
                                    or (acked and self.acknowledged_at > ack_deadline),
            "resolved": resolved,
            "resolve_breached": (not resolved and at > resolve_deadline)
                                or (resolved and self.resolved_at > resolve_deadline),
        }

    def runbook_steps(self) -> list[str]:
        return list(RUNBOOKS[self.runbook])


class TicketStore:
    """ServiceNow-style incident tickets, kept in sync with incidents.

    Ticket states: new -> in_progress -> resolved -> closed. A ticket is
    created from an incident, updated when the incident moves, and closed
    when the incident closes.
    """

    def __init__(self) -> None:
        self.tickets: dict[str, dict] = {}
        self._counter = 1000

    def create_from_incident(self, incident: Incident,
                             assignment_group: str) -> dict:
        number = f"INC-{self._counter}"
        self._counter += 1
        ticket = {
            "number": number,
            "incident_id": incident.incident_id,
            "short_description": incident.title,
            "severity": incident.severity,
            "service": incident.service,
            "assignment_group": assignment_group,
            "state": "new",
        }
        self.tickets[number] = ticket
        return ticket

    def sync(self, incident: Incident, ticket_number: str) -> dict:
        """Update a ticket to match its incident's state."""
        ticket = self.tickets.get(ticket_number)
        if ticket is None:
            raise KeyError(f"Unknown ticket: {ticket_number}")
        if ticket["incident_id"] != incident.incident_id:
            raise ValueError(
                f"Ticket {ticket_number} belongs to incident "
                f"{ticket['incident_id']}, not {incident.incident_id}")
        mapping = {"detected": "new", "triaged": "in_progress",
                   "mitigating": "in_progress", "resolved": "resolved",
                   "closed": "closed"}
        ticket["state"] = mapping[incident.state]
        return ticket


def incident_summary(incidents: list[Incident],
                     at: datetime | None = None) -> dict:
    """Fleet view: counts by state/severity and how many breached an SLA."""
    at = at or datetime.now(timezone.utc)
    by_state: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    breached = 0
    for incident in incidents:
        by_state[incident.state] = by_state.get(incident.state, 0) + 1
        by_severity[incident.severity] = by_severity.get(incident.severity, 0) + 1
        sla = incident.sla_status(at)
        if sla["acknowledge_breached"] or sla["resolve_breached"]:
            breached += 1
    return {"total": len(incidents), "by_state": by_state,
            "by_severity": by_severity, "sla_breached": breached}
