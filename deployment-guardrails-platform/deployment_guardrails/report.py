"""Fleet report: a human-readable text summary of the fleet."""

from __future__ import annotations

from deployment_guardrails.fleet import FleetDashboard
from deployment_guardrails.oncall import keep_the_lights_on_checklist


def render_fleet_report(dashboard: FleetDashboard) -> str:
    """Render the fleet dashboard as plain text."""
    lines = [
        "Deployment Guardrails -- Fleet Rollout Report",
        "=" * 50,
        "",
        f"Services tracked: {dashboard.service_count}",
        f"Deployable: {dashboard.deployable_count}  "
        f"Blocked: {dashboard.blocked_count}",
        f"Average safety score: {dashboard.average_safety_score}/100",
        "",
    ]
    for service in sorted(
        dashboard.services, key=lambda s: s.safety_score
    ):
        decision = service.decision
        lines.append(
            f"{service.service} {service.version} -- "
            f"{service.status.upper()} (safety {service.safety_score}/100)"
        )
        if decision is not None:
            lines.append(
                f"  Guardrails: {decision.passed_count}/"
                f"{decision.total_count} passed"
            )
            for violation in decision.violations:
                lines.append(f"    VIOLATION: {violation}")
        lines.append(
            f"  SLO: {service.availability:.3%} observed vs "
            f"{service.slo_target:.3%} target"
            + ("  [BREACHED]" if service.slo_breached else "")
        )
        lines.append(
            f"  Error budget: {service.error_budget_remaining_pct:.0f}% "
            f"remaining; open incidents: {service.open_incidents}"
        )
        lines.append("")
    riskiest = dashboard.riskiest()
    if riskiest is not None:
        lines.append(
            f"Riskiest service: {riskiest.service} "
            f"(safety {riskiest.safety_score}/100)"
        )
        lines.append("")
        lines.append(
            f"Keep-the-lights-on checklist -- {riskiest.service}:"
        )
        for item in keep_the_lights_on_checklist(riskiest):
            lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)
