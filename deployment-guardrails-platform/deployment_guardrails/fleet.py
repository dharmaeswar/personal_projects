"""Fleet rollout dashboard: per-service status and safety scores.

The fleet view combines the policy decision for a service with its
observed reliability: SLO target vs. observed availability, the
remaining error budget, and open incidents. From those it computes
a 0-100 safety score, so a team can see at a glance which services
are safe to deploy and which need attention first.

Safety score (0-100), all weights add to 100:
  - 40 points: guardrail pass rate (passed / total guardrails * 40)
  - 30 points: SLO health -- full 30 when availability meets the
    target, scaled down proportionally when it falls short
  - 20 points: error budget -- full 20 when budget remains, 0 when
    exhausted
  - 10 points: incidents -- 10 with no open incidents, minus 5 per
    open incident, floored at 0

Statuses: "deployable" (approved and score >= 80), "at risk"
(approved but score < 80, or score >= 80 but not approved),
"blocked" (not approved and score < 80).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deployment_guardrails.policies import PolicyDecision


@dataclass
class FleetService:
    """One service's fleet state: reliability numbers + policy result."""

    service: str
    version: str
    slo_target: float  # e.g. 0.999 for 99.9%
    availability: float  # observed availability, 0.0-1.0
    error_budget_remaining_pct: float  # 0-100
    open_incidents: int = 0
    decision: PolicyDecision | None = None

    @property
    def safety_score(self) -> int:
        """0-100 safety score from guardrails, SLO, budget, incidents."""
        guardrail_points = 0.0
        if self.decision is not None and self.decision.total_count:
            guardrail_points = (
                40.0 * self.decision.passed_count / self.decision.total_count
            )
        if self.availability >= self.slo_target:
            slo_points = 30.0
        elif self.slo_target > 0:
            slo_points = 30.0 * (self.availability / self.slo_target)
        else:
            slo_points = 0.0
        budget_points = 20.0 if self.error_budget_remaining_pct > 0 else 0.0
        incident_points = max(0.0, 10.0 - 5.0 * self.open_incidents)
        return int(round(guardrail_points + slo_points + budget_points + incident_points))

    @property
    def status(self) -> str:
        """deployable / at risk / blocked, from decision + score."""
        score = self.safety_score
        approved = bool(self.decision and self.decision.approved)
        if approved and score >= 80:
            return "deployable"
        if approved or score >= 80:
            return "at risk"
        return "blocked"

    @property
    def error_budget_used_pct(self) -> float:
        return round(100.0 - self.error_budget_remaining_pct, 1)

    @property
    def slo_breached(self) -> bool:
        return self.availability < self.slo_target


@dataclass
class FleetDashboard:
    """The whole fleet, with fleet-wide rollups."""

    services: list[FleetService] = field(default_factory=list)

    def add(self, service: FleetService) -> None:
        self.services.append(service)

    @property
    def service_count(self) -> int:
        return len(self.services)

    @property
    def deployable_count(self) -> int:
        return sum(1 for s in self.services if s.status == "deployable")

    @property
    def blocked_count(self) -> int:
        return sum(1 for s in self.services if s.status == "blocked")

    @property
    def average_safety_score(self) -> float:
        if not self.services:
            return 0.0
        return round(
            sum(s.safety_score for s in self.services) / len(self.services), 1
        )

    @property
    def services_with_open_incidents(self) -> list[FleetService]:
        return [s for s in self.services if s.open_incidents > 0]

    def riskiest(self) -> FleetService | None:
        """The service with the lowest safety score, or None."""
        if not self.services:
            return None
        return min(self.services, key=lambda s: s.safety_score)
