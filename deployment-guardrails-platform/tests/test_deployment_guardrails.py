"""Tests for the deployment guardrails platform."""

from __future__ import annotations

import pytest

from deployment_guardrails.audit import (
    connect,
    decisions_for_service,
    decisions_on_date,
    record_decision,
    rejection_count,
)
from deployment_guardrails.fleet import FleetDashboard, FleetService
from deployment_guardrails.oncall import (
    keep_the_lights_on_checklist,
    route_alert,
)
from deployment_guardrails.policies import (
    check_canary_stages,
    check_change_freeze,
    check_health_checks,
    check_oncall_owner,
    check_resource_limits,
    check_rollback_plan,
    evaluate_template,
    is_change_freeze,
)
from deployment_guardrails.report import render_fleet_report
from deployment_guardrails.templates import DeploymentTemplate, Registry


def clean_template(**overrides):
    """A template that passes every guardrail."""
    template = DeploymentTemplate(
        service="checkout-api",
        version="v2.4.0",
        owner="dharma",
        backup_owner="teammate-a",
        health_checks=["readiness-probe", "liveness-probe"],
        cpu_limit=2.0,
        memory_limit_mb=4096,
        canary_stages=[5, 25, 50, 100],
        rollback_plan={
            "previous_version": "v2.3.1",
            "steps": ["shift traffic back"],
            "automated": True,
        },
        deploy_hour_utc=14,
        deploy_day="tuesday",
    )
    for key, value in overrides.items():
        setattr(template, key, value)
    return template


def approved_service(**overrides):
    service = FleetService(
        service="checkout-api",
        version="v2.4.0",
        slo_target=0.999,
        availability=0.9995,
        error_budget_remaining_pct=62.0,
        open_incidents=0,
        decision=evaluate_template(clean_template()),
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


# --- policy engine: happy path ---

def test_clean_template_approved():
    decision = evaluate_template(clean_template())
    assert decision.approved
    assert decision.passed_count == 6
    assert decision.violations == []


def test_registry_round_trip():
    registry = Registry()
    registry.register_many([clean_template(), clean_template(service="search-api")])
    assert len(registry) == 2
    assert registry.get("search-api").version == "v2.4.0"
    assert registry.get("missing") is None
    assert registry.services() == ["checkout-api", "search-api"]


def test_template_from_dict_tolerates_missing_keys():
    template = DeploymentTemplate.from_dict({"service": "x", "version": "v1"})
    assert template.owner == ""
    assert template.health_checks == []
    assert template.canary_stages == []


# --- policy engine: each guardrail ---

def test_health_check_requires_both_probes():
    assert not check_health_checks(clean_template(health_checks=[])).passed
    assert not check_health_checks(
        clean_template(health_checks=["readiness-probe"])
    ).passed
    assert check_health_checks(
        clean_template(health_checks=["readiness-probe", "liveness-probe"])
    ).passed


def test_resource_limits_cap_and_missing():
    assert not check_resource_limits(clean_template(cpu_limit=8.0)).passed
    assert not check_resource_limits(clean_template(memory_limit_mb=16384)).passed
    assert not check_resource_limits(clean_template(cpu_limit=None)).passed
    assert check_resource_limits(clean_template(cpu_limit=4.0)).passed


def test_rollback_plan_requires_automated():
    plan = {"previous_version": "v2.3.1", "steps": ["shift back"]}
    assert not check_rollback_plan(clean_template(rollback_plan=plan)).passed
    plan["automated"] = True
    assert check_rollback_plan(clean_template(rollback_plan=plan)).passed
    assert not check_rollback_plan(clean_template(rollback_plan={})).passed


def test_canary_stages_must_start_small_and_end_at_100():
    assert not check_canary_stages(clean_template(canary_stages=[25, 100])).passed
    assert not check_canary_stages(clean_template(canary_stages=[5, 50])).passed
    assert not check_canary_stages(clean_template(canary_stages=[5, 50, 50, 100])).passed
    assert check_canary_stages(clean_template(canary_stages=[5, 50, 100])).passed


def test_oncall_owner_needs_distinct_backup():
    assert not check_oncall_owner(clean_template(backup_owner="")).passed
    assert not check_oncall_owner(clean_template(backup_owner="dharma")).passed
    assert check_oncall_owner(clean_template()).passed


def test_change_freeze_windows():
    assert is_change_freeze("saturday", 14)
    assert is_change_freeze("tuesday", 23)
    assert is_change_freeze("tuesday", 3)
    assert not is_change_freeze("tuesday", 14)
    assert not check_change_freeze(
        clean_template(deploy_day="saturday")
    ).passed
    assert check_change_freeze(clean_template()).passed


def test_noncompliant_template_lists_every_violation():
    decision = evaluate_template(
        clean_template(
            health_checks=["health-endpoint"],
            cpu_limit=8.0,
            memory_limit_mb=16384,
            canary_stages=[25, 100],
            backup_owner="",
            deploy_day="saturday",
            rollback_plan={"previous_version": "v1", "steps": ["x"]},
        )
    )
    assert not decision.approved
    assert decision.passed_count == 0
    assert len(decision.violations) == 6


# --- fleet dashboard / safety score ---

def test_safety_score_full_marks_for_clean_service():
    assert approved_service().safety_score == 100


def test_safety_score_drops_with_breaches():
    service = approved_service(
        availability=0.990,  # below 0.999 target
        error_budget_remaining_pct=0.0,
        open_incidents=2,
    )
    # 40 guardrails + ~29.7 SLO + 0 budget + 0 incidents = ~70
    assert service.safety_score == 70
    assert service.slo_breached
    assert service.error_budget_used_pct == 100.0


def test_fleet_statuses():
    dashboard = FleetDashboard()
    dashboard.add(approved_service())
    blocked = approved_service(
        service="billing-worker",
        availability=0.990,
        error_budget_remaining_pct=0.0,
        open_incidents=2,
        decision=evaluate_template(clean_template(health_checks=[])),
    )
    dashboard.add(blocked)
    assert dashboard.service_count == 2
    assert dashboard.deployable_count == 1
    assert dashboard.blocked_count == 1
    assert dashboard.riskiest().service == "billing-worker"
    assert dashboard.average_safety_score > 0


def test_fleet_dashboard_empty():
    dashboard = FleetDashboard()
    assert dashboard.average_safety_score == 0.0
    assert dashboard.riskiest() is None


# --- audit log ---

def test_audit_log_records_and_queries(tmp_path):
    conn = connect(tmp_path / "audit.db")
    decision = evaluate_template(clean_template())
    rejected = evaluate_template(clean_template(health_checks=[]))
    record_decision(conn, decision, "dharma", "2026-11-18 10:00:00 UTC")
    record_decision(conn, rejected, "dharma", "2026-11-18 11:00:00 UTC")
    record_decision(conn, decision, "teammate", "2026-11-17 09:00:00 UTC")

    entries = decisions_for_service(conn, "checkout-api")
    assert len(entries) == 3
    assert entries[0].decided_at.startswith("2026-11-18 11:00")
    assert not entries[0].approved
    assert "health check" in entries[0].violations

    today = decisions_on_date(conn, "2026-11-18")
    assert len(today) == 2
    assert rejection_count(conn) == 1
    assert rejection_count(conn, "checkout-api") == 1
    assert rejection_count(conn, "other-service") == 0


# --- on-call helper ---

def test_alert_routing_severities():
    sev1 = route_alert("sev1", "checkout-api", "dharma", "teammate-a")
    assert sev1.paged == ["dharma", "incident-commander"]
    assert sev1.escalation_minutes == 5
    assert sev1.channel == "page"
    assert sev1.escalation_target == "teammate-a"

    sev3 = route_alert("sev3", "checkout-api", "dharma", "teammate-a")
    assert sev3.channel == "ticket"
    assert sev3.escalation_minutes == 60

    unknown = route_alert("sev9", "checkout-api", "dharma", "teammate-a")
    assert unknown.channel == "ticket"  # falls back to sev3 rule


def test_keep_the_lights_on_checklist_flags_breaches():
    troubled = approved_service(
        service="billing-worker",
        availability=0.9931,
        slo_target=0.995,
        error_budget_remaining_pct=0.0,
        open_incidents=2,
        decision=evaluate_template(clean_template(health_checks=[])),
    )
    checklist = keep_the_lights_on_checklist(troubled)
    text = "\n".join(checklist)
    assert "SLO BREACHED" in text
    assert "Error budget EXHAUSTED" in text
    assert "2 open incident(s)" in text
    assert "REJECTED" in text
    assert "rollback path" in text.lower()

    clean = keep_the_lights_on_checklist(approved_service())
    clean_text = "\n".join(clean)
    assert "No open incidents" in clean_text
    assert "APPROVED" in clean_text


# --- report ---

def test_fleet_report_lists_violations_and_riskiest():
    dashboard = FleetDashboard()
    dashboard.add(approved_service())
    dashboard.add(
        approved_service(
            service="billing-worker",
            availability=0.9931,
            slo_target=0.995,
            error_budget_remaining_pct=0.0,
            open_incidents=2,
            decision=evaluate_template(clean_template(health_checks=[])),
        )
    )
    report = render_fleet_report(dashboard)
    assert "checkout-api" in report
    assert "billing-worker" in report
    assert "VIOLATION" in report
    assert "Riskiest service: billing-worker" in report
    assert "Keep-the-lights-on checklist" in report
