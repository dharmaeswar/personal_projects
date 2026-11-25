from ops.incident_triage import classify_severity, triage
from ops.release_gate import readiness_gate


def test_sev1_when_high_impact_and_urgency():
    assert classify_severity("high", "high") == "sev1"


def test_sev2_when_only_one_high():
    assert classify_severity("high", "low") == "sev2"
    assert classify_severity("low", "high") == "sev2"


def test_sev4_when_both_low():
    assert classify_severity("low", "low") == "sev4"


def test_triage_maps_runbook_and_sla():
    result = triage({"id": "INC-1", "kind": "stale-feed", "impact": "high", "urgency": "high"})
    assert result["severity"] == "sev1"
    assert result["sla_minutes"] == 15
    assert "stale-market-data-feed" in result["runbook"]
    assert "trading desk head" in result["escalate_to"]


def test_triage_unknown_kind_falls_back():
    result = triage({"id": "INC-2", "kind": "weird-thing", "impact": "low", "urgency": "low"})
    assert result["severity"] == "sev4"
    assert "general-triage" in result["runbook"]


def test_gate_go_when_all_pass():
    result = readiness_gate({
        "feeds_ok": True, "orders_ok": True, "latency_ok": True,
        "no_open_sev1": True, "runbooks_current": True,
    })
    assert result["verdict"] == "go"
    assert result["failing"] == []


def test_gate_no_go_lists_failures():
    result = readiness_gate({
        "feeds_ok": False, "orders_ok": True, "latency_ok": True,
        "no_open_sev1": True, "runbooks_current": False,
    })
    assert result["verdict"] == "no-go"
    assert result["failing"] == ["feeds_ok", "runbooks_current"]
