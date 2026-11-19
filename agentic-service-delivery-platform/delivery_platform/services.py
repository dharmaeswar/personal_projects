"""Service registry for the delivery platform.

A service is the unit the platform ships. Each service declares how it
wants to deploy: health checks, resource limits, canary stages, a rollback
plan, on-call owners, and a deploy window. All data is synthetic and local.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_CPU_CORES = 4
MAX_MEMORY_MB = 8192

VALID_CRITICALITY = ("standard", "critical")
VALID_STATUS = ("registered", "deploying", "live", "rolled-back")


@dataclass
class Service:
    name: str
    team: str
    owner: str
    backup_owner: str
    language: str
    repo: str
    region: str = "us-east-1"
    criticality: str = "standard"
    health_check: bool = True
    readiness_check: bool = True
    cpu_limit: float = 1.0
    memory_mb: int = 512
    canary_stages: list = field(default_factory=lambda: [5, 25, 50, 100])
    rollback_version: str = ""
    rollback_steps: list = field(default_factory=list)
    auto_rollback: bool = True
    deploy_window: str = "09:00-17:00"
    status: str = "registered"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "team": self.team,
            "owner": self.owner,
            "backup_owner": self.backup_owner,
            "language": self.language,
            "repo": self.repo,
            "region": self.region,
            "criticality": self.criticality,
            "health_check": self.health_check,
            "readiness_check": self.readiness_check,
            "cpu_limit": self.cpu_limit,
            "memory_mb": self.memory_mb,
            "canary_stages": list(self.canary_stages),
            "rollback_version": self.rollback_version,
            "rollback_steps": list(self.rollback_steps),
            "auto_rollback": self.auto_rollback,
            "deploy_window": self.deploy_window,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Service":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)


class ServiceRegistry:
    """In-memory registry of services the platform can ship."""

    def __init__(self) -> None:
        self._services: dict[str, Service] = {}

    def add(self, service: Service) -> None:
        if not service.name:
            raise ValueError("service name must not be empty")
        if service.name in self._services:
            raise ValueError(f"service already registered: {service.name}")
        if service.criticality not in VALID_CRITICALITY:
            raise ValueError(f"unknown criticality: {service.criticality}")
        if service.status not in VALID_STATUS:
            raise ValueError(f"unknown status: {service.status}")
        self._services[service.name] = service

    def get(self, name: str) -> Service | None:
        return self._services.get(name)

    def remove(self, name: str) -> None:
        if name not in self._services:
            raise ValueError(f"unknown service: {name}")
        del self._services[name]

    def list(self, team: str | None = None,
             criticality: str | None = None) -> list[Service]:
        out = list(self._services.values())
        if team is not None:
            out = [s for s in out if s.team == team]
        if criticality is not None:
            out = [s for s in out if s.criticality == criticality]
        return sorted(out, key=lambda s: s.name)

    def __len__(self) -> int:
        return len(self._services)
