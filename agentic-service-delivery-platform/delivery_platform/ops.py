"""Managed operations: region health, toil tracking, agentic remediation.

The operations side of the platform: for each region it tracks
availability, open incidents, and how much operational work is manual
toil versus automated, and it scores overall operational health. The
ops agent turns an incident into a remediation plan: low-risk actions
(restart, scale out, clear a cache) run automatically, medium- and
high-risk actions (traffic failover, config change, data repair) need an
explicit human approval, and a denied action escalates instead of
running. Every decision is written to the shared audit log, and every
automated action records the manual toil minutes it saved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .agent import AuditLog

# Minutes of manual operator work a successful automated action saves,
# by action type. These are planning estimates for the demo, not
# measured production figures.
TOIL_SAVED_MINUTES = {
    "restart-service": 25,
    "scale-out": 30,
    "clear-cache": 15,
    "failover-traffic": 90,
    "apply-config-change": 60,
    "repair-data": 120,
}

# Which remediation each severity maps to, and its risk. Low-risk
# actions auto-approve; medium/high need a human approval.
REMEDIATION_PLAN = {
    "sev1": ("failover-traffic", "high"),
    "sev2": ("restart-service", "low"),
    "sev3": ("clear-cache", "low"),
}

ACTION_DESCRIPTIONS = {
    "restart-service": "Restart the affected service instances",
    "scale-out": "Add capacity to the affected service",
    "clear-cache": "Clear the stale cache entries for the service",
    "failover-traffic": "Fail traffic over to the standby region",
    "apply-config-change": "Apply the corrected configuration",
    "repair-data": "Repair the corrupted records from backup",
}


@dataclass
class RegionHealth:
    """Operational state of one region for one week (synthetic)."""

    region: str
    services: int
    availability: float  # 0..1 over the week
    open_incidents: int
    manual_toil_hours: float
    automated_toil_hours: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.availability <= 1.0:
            raise ValueError("availability must be between 0 and 1")
        if self.services < 0 or self.open_incidents < 0:
            raise ValueError("services and open_incidents must not be negative")
        if self.manual_toil_hours < 0 or self.automated_toil_hours < 0:
            raise ValueError("toil hours must not be negative")

    @property
    def total_toil_hours(self) -> float:
        return self.manual_toil_hours + self.automated_toil_hours

    @property
    def automation_coverage(self) -> float:
        """Share of operational work already automated (0..1)."""
        total = self.total_toil_hours
        if total <= 0:
            return 0.0
        return self.automated_toil_hours / total

    def health_score(self) -> float:
        """Operational health, 0..100.

        50 points for availability (scaled from 0.99 to 1.0), 30 points
        for automation coverage, 20 points for incident load (a region
        loses 4 points per open incident, down to zero).
        """
        availability_points = max(
            0.0, min(50.0, (self.availability - 0.99) / 0.01 * 50.0))
        automation_points = 30.0 * self.automation_coverage
        incident_points = max(0.0, 20.0 - 4.0 * self.open_incidents)
        return round(availability_points + automation_points
                     + incident_points, 1)


@dataclass
class OpsIncident:
    incident_id: str
    service: str
    severity: str  # sev1 | sev2 | sev3
    title: str
    status: str = "open"

    def __post_init__(self) -> None:
        if self.severity not in REMEDIATION_PLAN:
            raise ValueError(f"unknown severity: {self.severity}")


@dataclass
class RemediationAction:
    name: str
    risk: str  # low | medium | high
    description: str
    requires_approval: bool = False
    toil_saved_minutes: int = 0


class OpsAgent:
    """Agentic-first incident response under approval gates."""

    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self.audit_log = audit_log if audit_log is not None else AuditLog()
        self.toil_saved_minutes = 0
        self.actions_run: list[str] = []

    def propose(self, incident: OpsIncident) -> RemediationAction:
        """Pick the remediation for an incident's severity."""
        name, risk = REMEDIATION_PLAN[incident.severity]
        action = RemediationAction(
            name=name,
            risk=risk,
            description=ACTION_DESCRIPTIONS[name],
            requires_approval=risk in ("medium", "high"),
            toil_saved_minutes=TOIL_SAVED_MINUTES[name],
        )
        self.audit_log.record(
            "agent", incident.service, f"propose-{name}", "proposed",
            f"{risk}-risk remediation for {incident.incident_id}: {name}",
        )
        return action

    def execute(self, incident: OpsIncident, action: RemediationAction,
                approved: bool | None = None,
                approver: str = "human:on-call") -> dict:
        """Run a proposed action, or escalate when approval is denied.

        An action that needs approval and has no explicit True approval
        is treated as denied: nothing risky runs without a human yes.
        Returns a result dict with the outcome and the toil saved.
        """
        if action.requires_approval:
            self.audit_log.record(
                approver if approved else approver,
                incident.service, action.name,
                "approved" if approved else "denied",
                f"{action.risk}-risk remediation "
                f"{'approved by human' if approved else 'no approval given'}",
            )
            if not approved:
                incident.status = "escalated"
                self.audit_log.record(
                    "agent", incident.service, "escalate", "executed",
                    f"{incident.incident_id} escalated to on-call "
                    "after denied approval",
                )
                return {
                    "incident": incident.incident_id,
                    "action": action.name,
                    "outcome": "denied",
                    "status": incident.status,
                    "toil_saved_minutes": 0,
                }
        else:
            self.audit_log.record(
                "agent", incident.service, action.name, "auto-approved",
                f"{action.risk}-risk remediation auto-approved under policy",
            )
        incident.status = "mitigated"
        self.toil_saved_minutes += action.toil_saved_minutes
        self.actions_run.append(action.name)
        self.audit_log.record(
            "agent", incident.service, action.name, "completed",
            f"{incident.incident_id} mitigated; "
            f"{action.toil_saved_minutes} manual toil minutes saved",
        )
        return {
            "incident": incident.incident_id,
            "action": action.name,
            "outcome": "completed",
            "status": incident.status,
            "toil_saved_minutes": action.toil_saved_minutes,
        }


def toil_report(regions: list[RegionHealth]) -> dict:
    """Aggregate manual vs automated toil across regions."""
    manual = sum(r.manual_toil_hours for r in regions)
    automated = sum(r.automated_toil_hours for r in regions)
    total = manual + automated
    return {
        "regions": len(regions),
        "manual_toil_hours": round(manual, 1),
        "automated_toil_hours": round(automated, 1),
        "automation_coverage": round(automated / total, 3) if total else 0.0,
        "health_scores": {r.region: r.health_score() for r in regions},
    }
