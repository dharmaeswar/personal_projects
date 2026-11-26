"""Tests for the identity extensibility Actions runtime."""

import pytest

from actions_runtime import ActionsService, AuthEvent, Trigger
from actions_runtime.actions import Action
from actions_runtime.cache import TenantCache
from actions_runtime.k8s import render_manifests
from actions_runtime.observability import AuditLog
from actions_runtime.sandbox import Sandbox
from actions_runtime.secrets import SecretStore, redact
from actions_runtime.tenancy import TenantRegistry, Tenant, check_same_tenant


def make_service(op_budget=100):
    svc = ActionsService(op_budget=op_budget)
    svc.create_tenant("acme", "Acme Corp")
    return svc


def login_event(tenant="acme", trigger=Trigger.POST_LOGIN):
    return AuthEvent(tenant_id=tenant, user_id="u1",
                     connection="Username-Password-Authentication",
                     trigger=trigger)


def test_post_login_action_adds_claim():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "tier", Trigger.POST_LOGIN,
                               [{"op": "set_claim", "key": "tier", "value": "enterprise"}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event())
    assert result.denied is False
    assert result.event.claims["tier"] == "enterprise"


def test_deny_action_blocks_flow():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "block", Trigger.PRE_TOKEN_ISSUANCE,
                               [{"op": "deny", "reason": "scope not granted"}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event(trigger=Trigger.PRE_TOKEN_ISSUANCE))
    assert result.denied is True
    assert "scope not granted" in result.deny_reason


def test_fail_closed_trigger_denies_on_action_error():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "boom", Trigger.PRE_TOKEN_ISSUANCE,
                               [{"op": "call_api", "endpoint": "no-such-endpoint"}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event(trigger=Trigger.PRE_TOKEN_ISSUANCE))
    assert result.denied is True
    assert "a1" in result.deny_reason


def test_fail_open_trigger_continues_after_action_error():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "boom", Trigger.POST_LOGIN,
                               [{"op": "call_api", "endpoint": "no-such-endpoint"}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event())
    assert result.denied is False
    assert result.action_results[0].error != ""


def test_op_budget_timeout():
    svc = make_service(op_budget=10)
    svc.register_action(Action("a1", "acme", "slow", Trigger.POST_LOGIN,
                               [{"op": "loop", "count": 25,
                                 "steps": [{"op": "log", "message": "tick"}]}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event())
    assert result.action_results[0].timed_out is True
    assert result.action_results[0].ops_used == 11


def test_unknown_op_rejected_at_registration():
    svc = make_service()
    with pytest.raises(ValueError, match="not allowed"):
        svc.register_action(Action("a1", "acme", "evil", Trigger.POST_LOGIN,
                                   [{"op": "exec", "code": "import os"}]))


def test_oversize_claim_rejected_in_sandbox():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "big", Trigger.POST_LOGIN,
                               [{"op": "set_claim", "key": "k", "value": "x" * 600}]))
    svc.deploy_action("acme", "a1")
    result = svc.invoke(login_event())
    assert "exceeds" in result.action_results[0].error


def test_cross_tenant_deploy_refused():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "x", Trigger.POST_LOGIN,
                               [{"op": "allow"}]))
    with pytest.raises(ValueError, match="not found for tenant"):
        svc.deploy_action("other-tenant", "a1")


def test_check_same_tenant_denies():
    with pytest.raises(PermissionError):
        check_same_tenant("acme", "globex")
    check_same_tenant("acme", "acme")  # same tenant passes


def test_secret_value_never_logged_in_plain_text():
    store = SecretStore()
    store.put("acme", "api-key", "sk-live-123456")
    assert redact("sk-live-123456") == "sk****56"
    assert "123456" not in redact("sk-live-123456")


def test_cache_is_per_tenant():
    cache = TenantCache()
    cache.put("acme", "tier", "enterprise")
    assert cache.get("acme", "tier") == "enterprise"
    assert cache.get("globex", "tier") is None


def test_idempotent_registration():
    svc = make_service()
    action = Action("a1", "acme", "x", Trigger.POST_LOGIN, [{"op": "allow"}])
    first = svc.register_action(action, idempotency_key="k1")
    second = svc.register_action(action, idempotency_key="k1")
    assert first == second
    assert len(svc.list_actions("acme")) == 1


def test_audit_chain_verifies_and_detects_tamper():
    log = AuditLog()
    log.append("acme", "a1", "post-login", "allow", "3 ops")
    log.append("acme", "a1", "post-login", "deny", "bad scope")
    assert log.verify_chain() is True
    log.entries[0].detail = "tampered"
    assert log.verify_chain() is False


def test_k8s_manifests_render_with_limits():
    manifests = render_manifests(namespace="actions", image_tag="1.0.0")
    assert "replicas: 3" in manifests["deployment.yaml"]
    assert "namespace: actions" in manifests["deployment.yaml"]
    assert "actions-runtime:1.0.0" in manifests["deployment.yaml"]
    assert "maxReplicas: 30" in manifests["hpa.yaml"]
    assert "memory: \"2Gi\"" in manifests["deployment.yaml"]


def test_health_reports_audit_chain():
    svc = make_service()
    health = svc.health()
    assert health["status"] == "ok"
    assert health["audit_chain_valid"] is True
    assert health["tenants"] == 1


def test_metrics_record_invocations_and_p95():
    svc = make_service()
    svc.register_action(Action("a1", "acme", "x", Trigger.POST_LOGIN,
                               [{"op": "set_claim", "key": "k", "value": "v"}]))
    svc.deploy_action("acme", "a1")
    for _ in range(3):
        svc.invoke(login_event())
    metrics = svc.runner.metrics["a1"]
    assert metrics.invocations == 3
    assert metrics.errors == 0
    assert metrics.p95_ms() == 1
