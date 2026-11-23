from delivery_platform.agent import AuditLog
from delivery_platform.ops import (
    OpsAgent,
    OpsIncident,
    RegionHealth,
    toil_report,
)


def make_region(**overrides):
    values = {
        "region": "us-west-2",
        "services": 42,
        "availability": 0.9995,
        "open_incidents": 1,
        "manual_toil_hours": 30.0,
        "automated_toil_hours": 70.0,
    }
    values.update(overrides)
    return RegionHealth(**values)


def test_health_score_is_bounded_zero_to_100():
    perfect = make_region(availability=1.0, open_incidents=0,
                          manual_toil_hours=0.0, automated_toil_hours=100.0)
    assert perfect.health_score() == 100.0
    worst = make_region(availability=0.90, open_incidents=10,
                        manual_toil_hours=100.0, automated_toil_hours=0.0)
    assert worst.health_score() == 0.0


def test_health_score_rewards_availability_automation_and_few_incidents():
    region = make_region()
    # availability 0.9995 -> 47.5 pts; coverage 0.7 -> 21 pts; 1 incident -> 16 pts
    assert region.health_score() == 84.5


def test_automation_coverage_is_zero_without_toil():
    region = make_region(manual_toil_hours=0.0, automated_toil_hours=0.0)
    assert region.automation_coverage == 0.0
    assert region.total_toil_hours == 0.0


def test_invalid_region_values_raise():
    import pytest
    with pytest.raises(ValueError):
        make_region(availability=1.5)
    with pytest.raises(ValueError):
        make_region(open_incidents=-1)
    with pytest.raises(ValueError):
        make_region(manual_toil_hours=-5.0)


def test_sev2_proposes_low_risk_restart_that_auto_approves():
    log = AuditLog()
    agent = OpsAgent(log)
    incident = OpsIncident("INC-101", "checkout-api", "sev2",
                           "elevated error rate")
    action = agent.propose(incident)
    assert action.name == "restart-service"
    assert action.risk == "low"
    assert action.requires_approval is False
    result = agent.execute(incident, action)
    assert result["outcome"] == "completed"
    assert result["toil_saved_minutes"] == 25
    assert incident.status == "mitigated"
    assert agent.toil_saved_minutes == 25
    assert agent.actions_run == ["restart-service"]


def test_sev1_proposes_high_risk_failover_needing_approval():
    agent = OpsAgent()
    incident = OpsIncident("INC-102", "checkout-api", "sev1",
                           "region unavailable")
    action = agent.propose(incident)
    assert action.name == "failover-traffic"
    assert action.risk == "high"
    assert action.requires_approval is True
    assert action.toil_saved_minutes == 90


def test_denied_high_risk_action_escalates_and_saves_no_toil():
    log = AuditLog()
    agent = OpsAgent(log)
    incident = OpsIncident("INC-102", "checkout-api", "sev1",
                           "region unavailable")
    action = agent.propose(incident)
    result = agent.execute(incident, action, approved=False)
    assert result["outcome"] == "denied"
    assert result["toil_saved_minutes"] == 0
    assert incident.status == "escalated"
    assert agent.toil_saved_minutes == 0
    assert agent.actions_run == []
    decisions = [e.decision for e in log.list()]
    assert "denied" in decisions
    assert "executed" in decisions  # the escalation entry


def test_missing_approval_is_treated_as_denied():
    agent = OpsAgent()
    incident = OpsIncident("INC-102", "checkout-api", "sev1",
                           "region unavailable")
    action = agent.propose(incident)
    result = agent.execute(incident, action)  # no approval given
    assert result["outcome"] == "denied"
    assert incident.status == "escalated"


def test_approved_high_risk_action_runs_and_saves_toil():
    agent = OpsAgent()
    incident = OpsIncident("INC-102", "checkout-api", "sev1",
                           "region unavailable")
    action = agent.propose(incident)
    result = agent.execute(incident, action, approved=True)
    assert result["outcome"] == "completed"
    assert result["toil_saved_minutes"] == 90
    assert incident.status == "mitigated"


def test_sev3_proposes_low_risk_cache_clear():
    agent = OpsAgent()
    incident = OpsIncident("INC-103", "search-api", "sev3", "stale results")
    action = agent.propose(incident)
    assert action.name == "clear-cache"
    assert action.requires_approval is False


def test_unknown_severity_raises():
    import pytest
    with pytest.raises(ValueError):
        OpsIncident("INC-104", "search-api", "sev4", "unknown")


def test_toil_report_aggregates_regions():
    regions = [make_region(),
               make_region(region="us-east-1", manual_toil_hours=10.0,
                           automated_toil_hours=10.0, availability=0.999,
                           open_incidents=0)]
    report = toil_report(regions)
    assert report["regions"] == 2
    assert report["manual_toil_hours"] == 40.0
    assert report["automated_toil_hours"] == 80.0
    assert report["automation_coverage"] == 0.667
    assert report["health_scores"]["us-west-2"] == 84.5
    # availability 0.999 -> 45 pts; coverage 0.5 -> 15 pts; 0 incidents -> 20 pts
    assert report["health_scores"]["us-east-1"] == 80.0
