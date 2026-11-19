from delivery_platform.agent import AgentWorkflow, AuditLog
from tests.test_services import make_service


def _approvals_for(steps):
    return {s.name: True for s in steps if s.requires_approval}


def test_plan_has_six_steps_with_approval_gates():
    workflow = AgentWorkflow()
    steps = workflow.plan_rollout(make_service(criticality="critical"))
    assert [s.name for s in steps] == [
        "validate-template", "canary-5", "canary-25",
        "canary-50", "full-rollout", "verify-slos",
    ]
    by_name = {s.name: s for s in steps}
    assert by_name["validate-template"].requires_approval is False
    assert by_name["canary-5"].requires_approval is False
    assert by_name["canary-25"].requires_approval is True
    assert by_name["full-rollout"].risk == "high"
    assert by_name["full-rollout"].requires_approval is True


def test_standard_service_full_rollout_is_medium_risk():
    workflow = AgentWorkflow()
    steps = workflow.plan_rollout(make_service(criticality="standard"))
    by_name = {s.name: s for s in steps}
    assert by_name["full-rollout"].risk == "medium"
    assert by_name["full-rollout"].requires_approval is True


def test_successful_rollout_goes_live_and_audits_every_step():
    log = AuditLog()
    workflow = AgentWorkflow(log)
    service = make_service()
    steps = workflow.plan_rollout(service)
    result = workflow.execute(service, steps, _approvals_for(steps))
    assert result["success"] is True
    assert result["blocked_at"] is None
    assert service.status == "live"
    assert len(result["steps"]) == 6
    assert len(log) == 1 + 6 + 1  # plan + 6 step decisions + completion


def test_guardrail_failure_blocks_before_any_traffic_moves():
    log = AuditLog()
    workflow = AgentWorkflow(log)
    service = make_service(cpu_limit=8.0)  # over the platform cap
    steps = workflow.plan_rollout(service)
    result = workflow.execute(service, steps, _approvals_for(steps))
    assert result["success"] is False
    assert result["blocked_at"] == "validate-template"
    assert "resource-limits" in result["reason"]
    assert service.status == "registered"
    assert result["steps"] == []


def test_denied_approval_stops_rollout_and_rolls_back():
    log = AuditLog()
    workflow = AgentWorkflow(log)
    service = make_service()
    steps = workflow.plan_rollout(service)
    approvals = _approvals_for(steps)
    approvals["canary-50"] = False  # human says no at 50%
    result = workflow.execute(service, steps, approvals)
    assert result["success"] is False
    assert result["blocked_at"] == "canary-50"
    assert service.status == "rolled-back"
    decisions = [e.decision for e in log.list()]
    assert "denied" in decisions
    assert "executed" in decisions  # the rollback entry


def test_missing_approval_is_treated_as_denied():
    workflow = AgentWorkflow()
    service = make_service()
    steps = workflow.plan_rollout(service)
    result = workflow.execute(service, steps, approvals={})
    assert result["success"] is False
    assert result["blocked_at"] == "canary-25"
    assert service.status == "rolled-back"


def test_audit_log_filters_by_service_and_limit():
    log = AuditLog()
    log.record("agent", "a", "plan-rollout", "planned", "x")
    log.record("agent", "b", "plan-rollout", "planned", "y")
    log.record("agent", "a", "canary-5", "completed", "z")
    assert len(log.list(service="a")) == 2
    assert len(log.list(limit=1)) == 1
    assert log.list(limit=1)[0].service == "a"
