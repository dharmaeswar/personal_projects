"""Policy engine: platform guardrails for deployment templates.

Six guardrails, each one a check over a service's declared template.
A template that fails any guardrail is REJECTED (no deploy), and
every failure is listed so the service owner can fix them all at
once instead of one at a time.

The guardrails:
  1. health_checks -- at least one readiness check and one liveness
     check must be declared (names must contain "readiness" /
     "liveness"; a single "health" check is not enough).
  2. resource_limits -- CPU and memory limits must be declared and
     stay inside the platform caps (max 4 CPU cores, max 8192 MB).
  3. rollback_plan -- must name a previous version, list rollback
     steps, and enable automated rollback.
  4. canary_stages -- must start at 5% or less, increase strictly,
     and end at 100%.
  5. oncall_owner -- a primary on-call owner and a backup owner must
     both be named, and they must be different people.
  6. change_freeze -- the planned deploy time must not fall inside a
     change-freeze window (weekends, or 22:00-06:00 UTC weekdays).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deployment_guardrails.templates import DeploymentTemplate

MAX_CPU_CORES = 4.0
MAX_MEMORY_MB = 8192
FREEZE_START_HOUR = 22  # 22:00 UTC
FREEZE_END_HOUR = 6  # 06:00 UTC
WEEKEND_DAYS = ("saturday", "sunday")


@dataclass
class PolicyResult:
    """Outcome of one guardrail check."""

    name: str
    passed: bool
    reason: str = ""
    detail: str = ""


@dataclass
class PolicyDecision:
    """Outcome of the full guardrail evaluation for one template."""

    service: str
    version: str
    approved: bool
    results: list[PolicyResult] = field(default_factory=list)

    @property
    def violations(self) -> list[str]:
        """Reasons from every failed guardrail, in check order."""
        return [r.reason for r in self.results if not r.passed]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)


def check_health_checks(template: DeploymentTemplate) -> PolicyResult:
    """Require a readiness check and a liveness check."""
    names = [h.lower() for h in template.health_checks]
    has_readiness = any("readiness" in h for h in names)
    has_liveness = any("liveness" in h for h in names)
    if not has_readiness and not has_liveness:
        return PolicyResult(
            name="health_checks",
            passed=False,
            reason="No readiness or liveness health check declared.",
        )
    missing = []
    if not has_readiness:
        missing.append("readiness")
    if not has_liveness:
        missing.append("liveness")
    if missing:
        return PolicyResult(
            name="health_checks",
            passed=False,
            reason="Missing health check(s): " + ", ".join(missing) + ".",
        )
    return PolicyResult(
        name="health_checks",
        passed=True,
        detail=f"{len(names)} health checks declared.",
    )


def check_resource_limits(template: DeploymentTemplate) -> PolicyResult:
    """CPU and memory limits must be declared and inside platform caps."""
    problems = []
    if template.cpu_limit is None:
        problems.append("no CPU limit declared")
    elif template.cpu_limit <= 0:
        problems.append("CPU limit must be above 0")
    elif template.cpu_limit > MAX_CPU_CORES:
        problems.append(
            f"CPU limit {template.cpu_limit} cores exceeds the "
            f"platform cap of {MAX_CPU_CORES} cores"
        )
    if template.memory_limit_mb is None:
        problems.append("no memory limit declared")
    elif template.memory_limit_mb <= 0:
        problems.append("memory limit must be above 0 MB")
    elif template.memory_limit_mb > MAX_MEMORY_MB:
        problems.append(
            f"memory limit {template.memory_limit_mb} MB exceeds the "
            f"platform cap of {MAX_MEMORY_MB} MB"
        )
    if problems:
        return PolicyResult(
            name="resource_limits",
            passed=False,
            reason="Resource limits invalid: " + "; ".join(problems) + ".",
        )
    return PolicyResult(
        name="resource_limits",
        passed=True,
        detail=f"{template.cpu_limit} CPU cores, "
        f"{template.memory_limit_mb} MB memory.",
    )


def check_rollback_plan(template: DeploymentTemplate) -> PolicyResult:
    """Rollback plan must name a previous version, list steps, and
    enable automated rollback."""
    plan = template.rollback_plan
    if not plan.get("previous_version"):
        return PolicyResult(
            name="rollback_plan",
            passed=False,
            reason="Rollback plan names no previous version.",
        )
    if not plan.get("steps"):
        return PolicyResult(
            name="rollback_plan",
            passed=False,
            reason="Rollback plan names a previous version but lists "
            "no steps to get there.",
        )
    if not plan.get("automated", False):
        return PolicyResult(
            name="rollback_plan",
            passed=False,
            reason="Rollback plan is manual only; automated rollback "
            "must be enabled.",
        )
    return PolicyResult(
        name="rollback_plan",
        passed=True,
        detail=f"Automated rollback to {plan['previous_version']} "
        f"in {len(plan['steps'])} step(s).",
    )


def check_canary_stages(template: DeploymentTemplate) -> PolicyResult:
    """Canary stages must start at 5% or less, increase strictly,
    and end at 100%."""
    stages = template.canary_stages
    if not stages:
        return PolicyResult(
            name="canary_stages",
            passed=False,
            reason="No canary stages declared; deploys must ramp "
            "traffic in stages.",
        )
    if stages[0] > 5:
        return PolicyResult(
            name="canary_stages",
            passed=False,
            reason=f"First canary stage is {stages[0]}% of traffic; "
            "it must start at 5% or less.",
        )
    if stages[-1] != 100:
        return PolicyResult(
            name="canary_stages",
            passed=False,
            reason=f"Canary stages end at {stages[-1]}%; they must "
            "end at 100%.",
        )
    if any(b <= a for a, b in zip(stages, stages[1:])):
        return PolicyResult(
            name="canary_stages",
            passed=False,
            reason="Canary stages must increase strictly: "
            + " -> ".join(str(s) for s in stages) + ".",
        )
    return PolicyResult(
        name="canary_stages",
        passed=True,
        detail="Canary ramp: " + " -> ".join(f"{s}%" for s in stages) + ".",
    )


def check_oncall_owner(template: DeploymentTemplate) -> PolicyResult:
    """A primary on-call owner and a different backup owner are
    required so a deploy is never owned by nobody."""
    if not template.owner:
        return PolicyResult(
            name="oncall_owner",
            passed=False,
            reason="No on-call owner named for this service.",
        )
    if not template.backup_owner:
        return PolicyResult(
            name="oncall_owner",
            passed=False,
            reason="No backup on-call owner named; a deploy needs "
            "a second person who can take over.",
        )
    if template.backup_owner == template.owner:
        return PolicyResult(
            name="oncall_owner",
            passed=False,
            reason="Backup on-call owner is the same person as the "
            "primary owner.",
        )
    return PolicyResult(
        name="oncall_owner",
        passed=True,
        detail=f"Owner {template.owner}, backup {template.backup_owner}.",
    )


def is_change_freeze(deploy_day: str, deploy_hour_utc: int) -> bool:
    """True when the planned deploy time falls in a freeze window:
    any weekend day, or 22:00-06:00 UTC on a weekday."""
    if deploy_day.lower() in WEEKEND_DAYS:
        return True
    return deploy_hour_utc >= FREEZE_START_HOUR or deploy_hour_utc < FREEZE_END_HOUR


def check_change_freeze(template: DeploymentTemplate) -> PolicyResult:
    """Deploys must not be scheduled inside a change-freeze window."""
    if is_change_freeze(template.deploy_day, template.deploy_hour_utc):
        when = (
            f"{template.deploy_day} {template.deploy_hour_utc:02d}:00 UTC"
        )
        return PolicyResult(
            name="change_freeze",
            passed=False,
            reason=f"Deploy scheduled at {when}, inside a "
            "change-freeze window (weekends, or 22:00-06:00 UTC).",
        )
    return PolicyResult(
        name="change_freeze",
        passed=True,
        detail=f"Scheduled {template.deploy_day} "
        f"{template.deploy_hour_utc:02d}:00 UTC, outside freeze windows.",
    )


GUARDRAILS = (
    check_health_checks,
    check_resource_limits,
    check_rollback_plan,
    check_canary_stages,
    check_oncall_owner,
    check_change_freeze,
)


def evaluate_template(template: DeploymentTemplate) -> PolicyDecision:
    """Run every guardrail over ``template`` and return the decision.

    The template is approved only when every guardrail passes.
    """
    results = [check(template) for check in GUARDRAILS]
    return PolicyDecision(
        service=template.service,
        version=template.version,
        approved=all(r.passed for r in results),
        results=results,
    )
