"""Agent-queryable data interface: the platform's data, AI-ready.

Agents (and humans) query platform state only through this read-only
surface: a fixed set of named queries with a published schema. There is
no way to mutate services, audit entries, or SLO samples through it, so
an agent can read everything it needs to plan a rollout without being
able to change platform state by accident.
"""
from __future__ import annotations

from .agent import AuditLog
from .policies import is_compliant
from .services import ServiceRegistry
from .slo import SLOTracker

QUERY_SCHEMA = {
    "query_service": {
        "description": "Full status of one service, with compliance and SLOs",
        "params": {"name": "service name (string)"},
        "returns": "service dict with compliance, slo summary, and audit count",
    },
    "list_services": {
        "description": "Services in the registry, optionally filtered",
        "params": {
            "team": "team name or null",
            "criticality": "'standard', 'critical', or null",
        },
        "returns": "list of service summaries",
    },
    "get_slo_summary": {
        "description": "SLO numbers and alerts for one service",
        "params": {"name": "service name (string)", "target": "SLO target 0..1"},
        "returns": "SLO summary dict",
    },
    "list_audit": {
        "description": "Audit-trail entries, newest last",
        "params": {"service": "service name or null", "limit": "max entries"},
        "returns": "list of audit entry dicts",
    },
}


class AgentDataInterface:
    """Read-only query surface over registry, audit log, and SLOs."""

    def __init__(self, registry: ServiceRegistry, audit_log: AuditLog,
                 slo_tracker: SLOTracker) -> None:
        self._registry = registry
        self._audit_log = audit_log
        self._slo = slo_tracker

    def describe_schema(self) -> dict:
        return dict(QUERY_SCHEMA)

    def _service_summary(self, service, target: float = 0.999) -> dict:
        data = service.to_dict()
        data["compliant"] = is_compliant(service)
        data["slo"] = self._slo.summary(service.name, target)
        data["audit_entries"] = len(self._audit_log.list(service.name))
        return data

    def query_service(self, name: str, target: float = 0.999) -> dict:
        service = self._registry.get(name)
        if service is None:
            raise ValueError(f"unknown service: {name}")
        if not 0 < target < 1:
            raise ValueError("target must be between 0 and 1")
        return self._service_summary(service, target)

    def list_services(self, team: str | None = None,
                      criticality: str | None = None) -> list[dict]:
        return [self._service_summary(s)
                for s in self._registry.list(team, criticality)]

    def get_slo_summary(self, name: str, target: float = 0.999) -> dict:
        if self._registry.get(name) is None:
            raise ValueError(f"unknown service: {name}")
        if not 0 < target < 1:
            raise ValueError("target must be between 0 and 1")
        return self._slo.summary(name, target)

    def list_audit(self, service: str | None = None,
                   limit: int = 50) -> list[dict]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if service is not None and self._registry.get(service) is None:
            raise ValueError(f"unknown service: {service}")
        return [e.to_dict()
                for e in self._audit_log.list(service, limit)]
