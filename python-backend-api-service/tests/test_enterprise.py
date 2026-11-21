"""Tests for the self-hosted enterprise server operations module."""

import json
import threading
import urllib.request

import pytest

from payments_api.app import create_server
from payments_api.enterprise import (
    EnterpriseStore,
    validate_check,
    validate_instance,
    validate_upgrade,
)
from payments_api.models import ValidationError


def _instance_fields(**overrides):
    fields = {
        "name": "acme-ghes",
        "environment": "on-premises",
        "version": "3.14.2",
        "node_count": 6,
    }
    fields.update(overrides)
    return fields


def _check(**overrides):
    check = {"service": "web", "status": "ok", "latency_ms": 42, "detail": ""}
    check.update(overrides)
    return check


class TestValidation:
    def test_valid_instance(self):
        assert validate_instance(_instance_fields())["node_count"] == 6

    def test_bad_environment_rejected(self):
        with pytest.raises(ValidationError):
            validate_instance(_instance_fields(environment="saas"))

    def test_bad_version_rejected(self):
        with pytest.raises(ValidationError):
            validate_instance(_instance_fields(version="3.14"))

    def test_node_count_bounds(self):
        with pytest.raises(ValidationError):
            validate_instance(_instance_fields(node_count=0))
        with pytest.raises(ValidationError):
            validate_instance(_instance_fields(node_count=65))

    def test_unknown_service_rejected(self):
        with pytest.raises(ValidationError):
            validate_check(_check(service="unicorn"))

    def test_bad_check_status_rejected(self):
        with pytest.raises(ValidationError):
            validate_check(_check(status="flapping"))

    def test_negative_latency_rejected(self):
        with pytest.raises(ValidationError):
            validate_check(_check(latency_ms=-1))

    def test_upgrade_requires_newer_version(self):
        with pytest.raises(ValidationError):
            validate_upgrade(
                {"target_version": "3.14.2", "backup_taken": True}, "3.14.2"
            )
        with pytest.raises(ValidationError):
            validate_upgrade(
                {"target_version": "3.13.9", "backup_taken": True}, "3.14.2"
            )

    def test_upgrade_requires_backup(self):
        with pytest.raises(ValidationError):
            validate_upgrade(
                {"target_version": "3.15.0", "backup_taken": False}, "3.14.2"
            )


class TestHealthAndAlerts:
    def test_unknown_health_with_no_checks(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        assert inst.aggregate_health() == "unknown"

    def test_all_ok_is_healthy(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        for service in ("web", "git", "redis", "mysql", "queue", "search"):
            inst.record_check(_check(service=service))
        assert inst.aggregate_health() == "healthy"

    def test_degraded_service_means_degraded(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        inst.record_check(_check(service="redis", status="degraded"))
        assert inst.aggregate_health() == "degraded"

    def test_down_service_means_down(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        inst.record_check(_check(service="mysql", status="down"))
        assert inst.aggregate_health() == "down"

    def test_two_failures_raise_alert_and_ok_resolves_it(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        inst.record_check(_check(service="queue", status="down"))
        assert store.active_alerts() == []
        inst.record_check(_check(service="queue", status="down"))
        alerts = store.active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["service"] == "queue"
        inst.record_check(_check(service="queue", status="ok"))
        assert store.active_alerts() == []

    def test_single_failure_raises_no_alert(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields())
        inst.record_check(_check(service="git", status="down"))
        assert store.active_alerts() == []


class TestUpgradePlanning:
    def test_batches_cover_all_nodes(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields(node_count=6))
        plan = inst.plan_upgrade(
            validate_upgrade(
                {"target_version": "3.15.0", "backup_taken": True}, "3.14.2"
            )
        )
        assert plan["from_version"] == "3.14.2"
        assert plan["to_version"] == "3.15.0"
        assert sum(b["nodes"] for b in plan["batches"]) == 6
        assert all("health_gate" in b for b in plan["batches"])

    def test_explicit_batch_size_respected(self):
        store = EnterpriseStore()
        inst = store.create_instance(_instance_fields(node_count=5))
        plan = inst.plan_upgrade(
            validate_upgrade(
                {"target_version": "3.15.0", "backup_taken": True, "batch_size": 2},
                "3.14.2",
            )
        )
        assert [b["nodes"] for b in plan["batches"]] == [2, 2, 1]


class TestHttpFlow:
    def _request(self, server, method, path, body=None):
        port = server.server_address[1]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_live_enterprise_flow(self):
        server = create_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, created = self._request(
                server, "POST", "/v1/enterprise/instances", _instance_fields()
            )
            assert status == 201
            inst_id = created["id"]
            assert created["health"] == "unknown"

            status, _ = self._request(
                server,
                "POST",
                f"/v1/enterprise/instances/{inst_id}/checks",
                _check(service="redis", status="down"),
            )
            assert status == 201
            status, _ = self._request(
                server,
                "POST",
                f"/v1/enterprise/instances/{inst_id}/checks",
                _check(service="redis", status="down"),
            )
            assert status == 201
            status, alerts = self._request(server, "GET", "/v1/enterprise/alerts")
            assert status == 200
            assert len(alerts["alerts"]) == 1

            status, health = self._request(
                server, "GET", f"/v1/enterprise/instances/{inst_id}/health"
            )
            assert status == 200
            assert health["health"] == "down"
            assert health["services"]["redis"] == "down"

            status, plan = self._request(
                server,
                "POST",
                f"/v1/enterprise/instances/{inst_id}/upgrades",
                {"target_version": "3.15.0", "backup_taken": True},
            )
            assert status == 201
            assert sum(b["nodes"] for b in plan["batches"]) == 6

            status, diag = self._request(
                server, "GET", f"/v1/enterprise/instances/{inst_id}/diagnostics"
            )
            assert status == 200
            assert diag["health"] == "down"
            assert len(diag["active_alerts"]) == 1
            assert len(diag["upgrade_plans"]) == 1
            assert diag["checks_recorded"] == 2

            status, bad = self._request(
                server,
                "POST",
                f"/v1/enterprise/instances/{inst_id}/upgrades",
                {"target_version": "3.14.2", "backup_taken": True},
            )
            assert status == 400
            status, missing = self._request(
                server, "GET", "/v1/enterprise/instances/inst_999999/health"
            )
            assert status == 404
        finally:
            server.shutdown()
            server.server_close()
