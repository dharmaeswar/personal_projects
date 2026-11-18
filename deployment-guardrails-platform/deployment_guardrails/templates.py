"""Deployment-template registry.

A service declares how it wants to deploy: which template it uses,
its health checks, resource limits, canary stages, rollback plan,
on-call owner, and the time window it wants to deploy in. The
registry holds every declared template and hands them to the policy
engine one at a time.

A template is a plain dict (loaded from JSON or YAML by the caller);
this module turns it into a validated ``DeploymentTemplate`` so the
policy checks always see the same shape, even when a service omits
a field.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeploymentTemplate:
    """One service's declared deployment configuration."""

    service: str
    version: str
    owner: str = ""
    backup_owner: str = ""
    health_checks: list[str] = field(default_factory=list)
    cpu_limit: float | None = None  # cores
    memory_limit_mb: int | None = None
    canary_stages: list[int] = field(default_factory=list)  # traffic %
    rollback_plan: dict = field(default_factory=dict)
    deploy_hour_utc: int = 12  # hour the deploy is scheduled, 0-23
    deploy_day: str = "monday"  # weekday name, lowercase

    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentTemplate":
        """Build a template from a raw dict, tolerating missing keys."""
        return cls(
            service=data.get("service", "unknown"),
            version=data.get("version", "unknown"),
            owner=data.get("owner", ""),
            backup_owner=data.get("backup_owner", ""),
            health_checks=list(data.get("health_checks", [])),
            cpu_limit=data.get("cpu_limit"),
            memory_limit_mb=data.get("memory_limit_mb"),
            canary_stages=list(data.get("canary_stages", [])),
            rollback_plan=dict(data.get("rollback_plan", {})),
            deploy_hour_utc=data.get("deploy_hour_utc", 12),
            deploy_day=str(data.get("deploy_day", "monday")).lower(),
        )


class Registry:
    """The set of deployment templates declared across the fleet."""

    def __init__(self) -> None:
        self._templates: dict[str, DeploymentTemplate] = {}

    def register(self, template: DeploymentTemplate) -> None:
        """Add (or replace) the template for a service."""
        self._templates[template.service] = template

    def register_many(self, templates: list[DeploymentTemplate]) -> None:
        for template in templates:
            self.register(template)

    def get(self, service: str) -> DeploymentTemplate | None:
        return self._templates.get(service)

    def services(self) -> list[str]:
        """Service names in registration order."""
        return list(self._templates)

    def all_templates(self) -> list[DeploymentTemplate]:
        return list(self._templates.values())

    def __len__(self) -> int:
        return len(self._templates)
