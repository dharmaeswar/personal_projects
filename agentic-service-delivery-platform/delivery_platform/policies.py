"""Deployment guardrails.

Every service template is checked against six shared guardrails before
any rollout step runs. A finding names the guardrail, whether it passed,
and why. Nothing here deploys anything; it only judges a template.
"""
from __future__ import annotations

from dataclasses import dataclass

from .services import MAX_CPU_CORES, MAX_MEMORY_MB, Service


@dataclass
class Finding:
    guardrail: str
    passed: bool
    detail: str


def _parse_window(window: str) -> tuple[int, int] | None:
    """Parse 'HH:MM-HH:MM' into (start_minutes, end_minutes) or None."""
    try:
        start, end = window.split("-")
        sh, sm = (int(p) for p in start.split(":"))
        eh, em = (int(p) for p in end.split(":"))
        if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
            return None
        return sh * 60 + sm, eh * 60 + em
    except (ValueError, AttributeError):
        return None


def check_health_checks(service: Service) -> Finding:
    passed = bool(service.health_check and service.readiness_check)
    return Finding(
        "health-checks", passed,
        "liveness and readiness checks present"
        if passed else "missing liveness or readiness check",
    )


def check_resource_limits(service: Service) -> Finding:
    passed = (0 < service.cpu_limit <= MAX_CPU_CORES
              and 0 < service.memory_mb <= MAX_MEMORY_MB)
    return Finding(
        "resource-limits", passed,
        f"cpu={service.cpu_limit} cores, memory={service.memory_mb} MB "
        f"within caps ({MAX_CPU_CORES} cores, {MAX_MEMORY_MB} MB)"
        if passed else
        f"cpu={service.cpu_limit} cores or memory={service.memory_mb} MB "
        f"outside caps ({MAX_CPU_CORES} cores, {MAX_MEMORY_MB} MB)",
    )


def check_canary_shape(service: Service) -> Finding:
    stages = service.canary_stages or []
    passed = (len(stages) >= 2 and stages[0] <= 5 and stages[-1] == 100
              and all(b > a for a, b in zip(stages, stages[1:])))
    return Finding(
        "canary-shape", passed,
        f"canary stages {stages} start at 5% or less, rise, and end at 100%"
        if passed else
        f"canary stages {stages} must start at 5% or less, rise strictly, "
        "and end at 100%",
    )


def check_rollback_plan(service: Service) -> Finding:
    passed = (bool(service.rollback_version)
              and len(service.rollback_steps) > 0
              and bool(service.auto_rollback))
    return Finding(
        "rollback-plan", passed,
        f"rollback to {service.rollback_version} with "
        f"{len(service.rollback_steps)} steps and auto-rollback on"
        if passed else
        "rollback plan needs a version, at least one step, and auto-rollback",
    )


def check_on_call(service: Service) -> Finding:
    passed = (bool(service.owner) and bool(service.backup_owner)
              and service.owner != service.backup_owner)
    return Finding(
        "on-call", passed,
        f"primary {service.owner} with different backup {service.backup_owner}"
        if passed else
        "need a primary on-call owner and a different backup owner",
    )


def check_deploy_window(service: Service) -> Finding:
    parsed = _parse_window(service.deploy_window)
    passed = parsed is not None and parsed[0] < parsed[1]
    return Finding(
        "deploy-window", passed,
        f"deploy window {service.deploy_window} is a valid daytime window"
        if passed else
        f"deploy window {service.deploy_window!r} is not a valid HH:MM-HH:MM "
        "window with start before end",
    )


CHECKS = (
    check_health_checks,
    check_resource_limits,
    check_canary_shape,
    check_rollback_plan,
    check_on_call,
    check_deploy_window,
)


def evaluate_service(service: Service) -> list[Finding]:
    """Run every guardrail over one service template."""
    return [check(service) for check in CHECKS]


def is_compliant(service: Service) -> bool:
    return all(f.passed for f in evaluate_service(service))


def failing_guardrails(service: Service) -> list[str]:
    return [f.guardrail for f in evaluate_service(service) if not f.passed]
