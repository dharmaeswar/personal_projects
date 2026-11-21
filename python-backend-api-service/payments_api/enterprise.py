"""Self-hosted enterprise server operations (stdlib only).

Models the operations side of a self-hosted, enterprise-grade developer
platform — the kind of product GitHub Enterprise Server is: the same
software as the hosted service, deployed on a customer's own on-premises
data center or cloud, where the vendor's engineers must plan, monitor
and troubleshoot the deployment remotely.

What it covers:
- Instance registry: self-hosted instances with environment, version and
  node count.
- Health checks: per-service checks for the platform's components
  (web/unicorn, git, redis, mysql, queue/resque, search) with latency.
- Aggregate health: healthy / degraded / down from the latest checks.
- Alerting: two consecutive failed checks on one service raise an alert;
  a passing check resolves it.
- Rolling upgrades: a version upgrade is planned in node batches with a
  backup requirement and a health gate between batches.
- Diagnostics bundle: instance summary, latest per-service status,
  active alerts and upgrade plans, for troubleshooting a customer site.

Everything is in-memory and simulated: no real cluster, container
orchestrator or customer site is contacted. The code models the
operations logic — validation, aggregation, batching, alerting — that
an enterprise-server team ships around those systems.
"""

from __future__ import annotations

import itertools
import threading

from .models import ValidationError

SERVICES = ("web", "git", "redis", "mysql", "queue", "search")
ENVIRONMENTS = ("on-premises", "cloud")
CHECK_STATUSES = ("ok", "degraded", "down")
ALERT_THRESHOLD = 2


def _require_str(value, field: str, max_len: int = 120) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} is required")
    if len(value) > max_len:
        raise ValidationError(f"{field} is too long")
    return value.strip()


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValidationError("version must be MAJOR.MINOR.PATCH, e.g. 3.14.2")
    return tuple(int(p) for p in parts)


def validate_instance(body: dict) -> dict:
    """Validate an instance registration payload."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    name = _require_str(body.get("name"), "name")
    environment = body.get("environment")
    if environment not in ENVIRONMENTS:
        raise ValidationError("environment must be 'on-premises' or 'cloud'")
    version = _require_str(body.get("version"), "version")
    _parse_version(version)
    node_count = body.get("node_count")
    if not isinstance(node_count, int) or isinstance(node_count, bool):
        raise ValidationError("node_count must be an integer")
    if node_count < 1 or node_count > 64:
        raise ValidationError("node_count must be between 1 and 64")
    return {
        "name": name,
        "environment": environment,
        "version": version,
        "node_count": node_count,
    }


def validate_check(body: dict) -> dict:
    """Validate one per-service health check result."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    service = body.get("service")
    if service not in SERVICES:
        raise ValidationError(f"service must be one of {', '.join(SERVICES)}")
    status = body.get("status")
    if status not in CHECK_STATUSES:
        raise ValidationError("status must be 'ok', 'degraded' or 'down'")
    latency_ms = body.get("latency_ms")
    if not isinstance(latency_ms, (int, float)) or isinstance(latency_ms, bool):
        raise ValidationError("latency_ms must be a number")
    if latency_ms < 0:
        raise ValidationError("latency_ms must be zero or positive")
    detail = body.get("detail", "")
    if not isinstance(detail, str):
        raise ValidationError("detail must be a string")
    return {
        "service": service,
        "status": status,
        "latency_ms": latency_ms,
        "detail": detail,
    }


def validate_upgrade(body: dict, current_version: str) -> dict:
    """Validate a rolling-upgrade plan request."""
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    target = _require_str(body.get("target_version"), "target_version")
    target_parts = _parse_version(target)
    if target_parts <= _parse_version(current_version):
        raise ValidationError("target_version must be newer than the current version")
    if body.get("backup_taken") is not True:
        raise ValidationError("backup_taken must be true before an upgrade is planned")
    batch_size = body.get("batch_size")
    if batch_size is not None:
        if not isinstance(batch_size, int) or isinstance(batch_size, bool):
            raise ValidationError("batch_size must be an integer")
        if batch_size < 1:
            raise ValidationError("batch_size must be at least 1")
    return {"target_version": target, "batch_size": batch_size}


class Instance:
    """One self-hosted enterprise instance and its operations state."""

    def __init__(self, instance_id: str, fields: dict) -> None:
        self.id = instance_id
        self.name = fields["name"]
        self.environment = fields["environment"]
        self.version = fields["version"]
        self.node_count = fields["node_count"]
        self.checks: list[dict] = []
        self.alerts: list[dict] = []
        self.upgrades: list[dict] = []
        self._fail_streaks: dict[str, int] = {s: 0 for s in SERVICES}
        self._alert_counter = itertools.count(1)
        self._upgrade_counter = itertools.count(1)

    def latest_status(self, service: str) -> str | None:
        for check in reversed(self.checks):
            if check["service"] == service:
                return check["status"]
        return None

    def aggregate_health(self) -> str:
        """healthy / degraded / down / unknown from the latest checks."""
        statuses = [self.latest_status(s) for s in SERVICES]
        seen = [s for s in statuses if s is not None]
        if not seen:
            return "unknown"
        if "down" in seen:
            return "down"
        if "degraded" in seen:
            return "degraded"
        return "healthy"

    def record_check(self, check: dict) -> dict:
        """Record a check and raise/resolve alerts on failure streaks."""
        self.checks.append(check)
        service = check["service"]
        if check["status"] == "down":
            self._fail_streaks[service] += 1
            if self._fail_streaks[service] == ALERT_THRESHOLD:
                alert = {
                    "id": f"alrt_{next(self._alert_counter):06d}",
                    "instance_id": self.id,
                    "service": service,
                    "status": "active",
                    "message": (
                        f"{service} failed {ALERT_THRESHOLD} consecutive "
                        f"health checks on instance {self.name}"
                    ),
                }
                self.alerts.append(alert)
        else:
            self._fail_streaks[service] = 0
            for alert in self.alerts:
                if alert["service"] == service and alert["status"] == "active":
                    alert["status"] = "resolved"
        return check

    def plan_upgrade(self, fields: dict) -> dict:
        """Plan a rolling upgrade in node batches with a health gate."""
        batch_size = fields["batch_size"] or max(1, self.node_count // 3)
        batches = []
        remaining = self.node_count
        batch_no = 1
        while remaining > 0:
            take = min(batch_size, remaining)
            batches.append(
                {
                    "batch": batch_no,
                    "nodes": take,
                    "health_gate": "instance must be healthy before this batch starts",
                }
            )
            remaining -= take
            batch_no += 1
        plan = {
            "id": f"upg_{next(self._upgrade_counter):06d}",
            "instance_id": self.id,
            "from_version": self.version,
            "to_version": fields["target_version"],
            "backup_taken": True,
            "batches": batches,
            "status": "planned",
        }
        self.upgrades.append(plan)
        return plan

    def diagnostics(self) -> dict:
        return {
            "instance_id": self.id,
            "name": self.name,
            "environment": self.environment,
            "version": self.version,
            "node_count": self.node_count,
            "health": self.aggregate_health(),
            "services": {
                service: self.latest_status(service) for service in SERVICES
            },
            "active_alerts": [a for a in self.alerts if a["status"] == "active"],
            "checks_recorded": len(self.checks),
            "upgrade_plans": self.upgrades,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "environment": self.environment,
            "version": self.version,
            "node_count": self.node_count,
            "health": self.aggregate_health(),
        }


class EnterpriseStore:
    """Thread-safe registry of self-hosted enterprise instances."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instances: dict[str, Instance] = {}
        self._counter = itertools.count(1)

    def create_instance(self, fields: dict) -> Instance:
        with self._lock:
            instance_id = f"inst_{next(self._counter):06d}"
            instance = Instance(instance_id, fields)
            self._instances[instance_id] = instance
            return instance

    def get_instance(self, instance_id: str) -> Instance | None:
        with self._lock:
            return self._instances.get(instance_id)

    def active_alerts(self) -> list[dict]:
        with self._lock:
            alerts = []
            for instance in self._instances.values():
                alerts.extend(a for a in instance.alerts if a["status"] == "active")
            return alerts
