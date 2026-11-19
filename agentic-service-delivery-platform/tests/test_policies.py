from delivery_platform.policies import (
    evaluate_service,
    failing_guardrails,
    is_compliant,
)
from tests.test_services import make_service


def test_compliant_service_passes_all():
    service = make_service()
    assert is_compliant(service)
    assert failing_guardrails(service) == []


def test_missing_health_check_fails():
    service = make_service(health_check=False)
    assert failing_guardrails(service) == ["health-checks"]


def test_missing_readiness_check_fails():
    service = make_service(readiness_check=False)
    assert "health-checks" in failing_guardrails(service)


def test_resource_caps_enforced():
    assert "resource-limits" in failing_guardrails(make_service(cpu_limit=8.0))
    assert "resource-limits" in failing_guardrails(make_service(memory_mb=16384))
    assert "resource-limits" in failing_guardrails(make_service(cpu_limit=0))
    assert is_compliant(make_service(cpu_limit=4.0, memory_mb=8192))


def test_canary_shape_rules():
    assert "canary-shape" in failing_guardrails(make_service(canary_stages=[10, 100]))
    assert "canary-shape" in failing_guardrails(make_service(canary_stages=[5, 100, 50]))
    assert "canary-shape" in failing_guardrails(make_service(canary_stages=[5, 50]))
    assert "canary-shape" in failing_guardrails(make_service(canary_stages=[]))
    assert is_compliant(make_service(canary_stages=[5, 25, 50, 100]))


def test_rollback_plan_rules():
    assert "rollback-plan" in failing_guardrails(make_service(rollback_version=""))
    assert "rollback-plan" in failing_guardrails(make_service(rollback_steps=[]))
    assert "rollback-plan" in failing_guardrails(make_service(auto_rollback=False))


def test_on_call_needs_two_different_owners():
    assert "on-call" in failing_guardrails(make_service(backup_owner=""))
    assert "on-call" in failing_guardrails(make_service(backup_owner="dharma"))


def test_deploy_window_rules():
    assert "deploy-window" in failing_guardrails(make_service(deploy_window="17:00-09:00"))
    assert "deploy-window" in failing_guardrails(make_service(deploy_window="not-a-window"))
    assert "deploy-window" in failing_guardrails(make_service(deploy_window="09:00-09:00"))
    assert is_compliant(make_service(deploy_window="08:30-16:30"))


def test_evaluate_returns_all_six_guardrails():
    findings = evaluate_service(make_service())
    assert [f.guardrail for f in findings] == [
        "health-checks", "resource-limits", "canary-shape",
        "rollback-plan", "on-call", "deploy-window",
    ]
    assert all(f.passed for f in findings)
