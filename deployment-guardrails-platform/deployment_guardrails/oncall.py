"""On-call helper: alert routing and keep-the-lights-on checklists.

Alert routing maps a severity to the people who get paged first and
how long before it escalates to the next person, so an alert never
sits with one person who is away. The checklist generator builds
the runbook a responder works through when a service pages: verify
the service is up, check the error budget, look at recent deploys,
and confirm the rollback path -- with the service's own numbers
filled in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deployment_guardrails.fleet import FleetService

# severity -> (first responders, escalation delay in minutes, channel)
ROUTING_RULES: dict[str, tuple[list[str], int, str]] = {
    "sev1": (["primary_oncall", "incident_commander"], 5, "page"),
    "sev2": (["primary_oncall"], 15, "page"),
    "sev3": (["primary_oncall"], 60, "ticket"),
    "sev4": (["service_owner"], 240, "ticket"),
}

SEVERITY_ORDER = ("sev1", "sev2", "sev3", "sev4")


@dataclass
class AlertRoute:
    """Where one alert goes, and how fast it escalates."""

    severity: str
    service: str
    paged: list[str]
    escalation_minutes: int
    channel: str
    escalation_target: str = ""


def route_alert(
    severity: str, service: str, owner: str, backup_owner: str
) -> AlertRoute:
    """Route an alert for ``service`` at ``severity``.

    ``owner`` fills the primary_oncall slot, ``backup_owner`` the
    escalation target. Unknown severities fall back to the sev3
    ticket rule instead of failing silently.
    """
    severity = severity.lower()
    roles, delay, channel = ROUTING_RULES.get(
        severity, ROUTING_RULES["sev3"]
    )
    paged = [
        owner if role == "primary_oncall"
        else "incident-commander" if role == "incident_commander"
        else backup_owner if role == "service_owner"
        else role
        for role in roles
    ]
    # A sev1 pages the incident commander too; the backup owner is
    # the escalation target for every severity.
    return AlertRoute(
        severity=severity,
        service=service,
        paged=paged,
        escalation_minutes=delay,
        channel=channel,
        escalation_target=backup_owner,
    )


def keep_the_lights_on_checklist(service: FleetService) -> list[str]:
    """Build the on-call checklist for one service, with its own
    numbers filled in. Items are ordered: confirm the service,
    check the budget, look at what changed, confirm the way back."""
    items = [
        f"Confirm {service.service} {service.version} is serving "
        f"traffic (availability {service.availability:.3%}, "
        f"SLO target {service.slo_target:.3%}).",
    ]
    if service.slo_breached:
        items.append(
            f"SLO BREACHED: availability {service.availability:.3%} is "
            f"below the {service.slo_target:.3%} target -- open an "
            "incident and freeze deploys for this service."
        )
    items.append(
        f"Error budget: {service.error_budget_remaining_pct:.0f}% "
        f"remaining ({service.error_budget_used_pct:.0f}% used)."
    )
    if service.error_budget_remaining_pct <= 0:
        items.append(
            "Error budget EXHAUSTED: no new deploys until the budget "
            "recovers; reliability work takes priority over features."
        )
    if service.open_incidents:
        items.append(
            f"{service.open_incidents} open incident(s) -- check the "
            "incident channel before changing anything."
        )
    else:
        items.append("No open incidents -- confirm in the incident tracker.")
    if service.decision is not None:
        if service.decision.approved:
            items.append(
                f"Last policy decision: APPROVED "
                f"({service.decision.passed_count}/"
                f"{service.decision.total_count} guardrails passed)."
            )
        else:
            items.append(
                "Last policy decision: REJECTED -- "
                + "; ".join(service.decision.violations)
            )
    items.append(
        "Confirm the rollback path before any change: previous version "
        "named, steps listed, automated rollback enabled."
    )
    return items
