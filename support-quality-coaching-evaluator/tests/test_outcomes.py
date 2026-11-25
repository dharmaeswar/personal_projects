"""Tests for production observability and outcome tracking (Support AI)."""

import pytest

from support_quality.outcomes import (
    ConversationOutcome,
    alert_check,
    detect_regression,
    generate_outcomes,
    outcome_summary,
    vendor_health,
)


def _outcome(**kwargs):
    base = dict(
        conversation_id="CONV-0001",
        channel="chat",
        resolved_without_human=True,
        escalated=False,
        turns=4,
        latency_ms=[400, 450, 500, 420],
        vendor="vendor-a",
        vendor_errors=0,
        csat=4.5,
        cost_usd=0.05,
    )
    base.update(kwargs)
    return ConversationOutcome(**base)


def test_generate_outcomes_is_seeded():
    first = generate_outcomes(seed=11, n=50)
    second = generate_outcomes(seed=11, n=50)
    assert [o.conversation_id for o in first] == [o.conversation_id for o in second]
    assert [o.resolved_without_human for o in first] == [o.resolved_without_human for o in second]
    assert len(first) == 50


def test_summary_rates_match_inputs():
    outcomes = [
        _outcome(conversation_id="C1", resolved_without_human=True, escalated=False),
        _outcome(conversation_id="C2", resolved_without_human=False, escalated=True),
        _outcome(conversation_id="C3", resolved_without_human=True, escalated=False),
        _outcome(conversation_id="C4", resolved_without_human=False, escalated=True),
    ]
    summary = outcome_summary(outcomes)
    assert summary["n_conversations"] == 4
    assert summary["resolution_rate"] == pytest.approx(0.5)
    assert summary["escalation_rate"] == pytest.approx(0.5)
    assert summary["mean_turns"] == pytest.approx(4.0)
    assert summary["mean_latency_ms"] == pytest.approx(442.5)
    assert summary["mean_csat"] == pytest.approx(4.5)
    assert summary["csat_responses"] == 4


def test_summary_rejects_empty_input():
    with pytest.raises(ValueError, match="no outcomes"):
        outcome_summary([])


def test_summary_ignores_missing_csat():
    outcomes = [
        _outcome(conversation_id="C1", csat=None),
        _outcome(conversation_id="C2", csat=5.0),
    ]
    summary = outcome_summary(outcomes)
    assert summary["mean_csat"] == pytest.approx(5.0)
    assert summary["csat_responses"] == 1


def test_seeded_panel_resolves_more_on_chat():
    outcomes = generate_outcomes(seed=11, n=400)
    chat = [o for o in outcomes if o.channel == "chat"]
    voice = [o for o in outcomes if o.channel == "voice"]
    assert outcome_summary(chat)["resolution_rate"] > outcome_summary(voice)["resolution_rate"]


def test_detect_regression_flags_resolution_drop():
    baseline = {"resolution_rate": 0.75, "p95_latency_ms": 1000.0}
    current = {"resolution_rate": 0.65, "p95_latency_ms": 1050.0}
    result = detect_regression(baseline, current)
    assert result["regressed"] is True
    assert result["resolution_delta"] == pytest.approx(-0.10)
    assert any("resolution rate fell" in f for f in result["findings"])


def test_detect_regression_flags_latency_rise():
    baseline = {"resolution_rate": 0.75, "p95_latency_ms": 1000.0}
    current = {"resolution_rate": 0.74, "p95_latency_ms": 1400.0}
    result = detect_regression(baseline, current)
    assert result["regressed"] is True
    assert result["p95_delta_pct"] == pytest.approx(40.0)
    assert any("p95 latency rose" in f for f in result["findings"])


def test_detect_regression_passes_stable_release():
    baseline = {"resolution_rate": 0.75, "p95_latency_ms": 1000.0}
    current = {"resolution_rate": 0.74, "p95_latency_ms": 1050.0}
    result = detect_regression(baseline, current)
    assert result["regressed"] is False
    assert result["findings"] == []


def test_vendor_health_flags_unreliable_vendor():
    outcomes = generate_outcomes(seed=11, n=400)
    health = vendor_health(outcomes)
    assert set(health) == {"vendor-a", "vendor-b"}
    # vendor-b is seeded with a 5x error rate; vendor-a stays within SLO.
    assert health["vendor-b"]["error_rate"] > health["vendor-a"]["error_rate"]
    assert health["vendor-b"]["breaching_slo"] is True
    assert health["vendor-a"]["breaching_slo"] is False


def test_alert_check_fires_on_bad_summary():
    summary = {
        "resolution_rate": 0.50,
        "escalation_rate": 0.45,
        "p95_latency_ms": 2500.0,
        "vendor_error_rate": 0.05,
    }
    alerts = alert_check(summary)
    assert len(alerts) == 4


def test_alert_check_is_quiet_on_healthy_summary():
    outcomes = generate_outcomes(seed=11, n=400)
    healthy = [o for o in outcomes if o.channel == "chat" and o.vendor == "vendor-a"]
    summary = outcome_summary(healthy)
    # The chat + reliable-vendor slice is healthy on every threshold:
    # resolution ~78%, escalation ~27%, p95 latency ~800ms, error rate ~1%.
    assert alert_check(summary) == []


def test_alert_check_uses_custom_thresholds():
    summary = {
        "resolution_rate": 0.70,
        "escalation_rate": 0.20,
        "p95_latency_ms": 1200.0,
        "vendor_error_rate": 0.01,
    }
    assert alert_check(summary, thresholds={"min_resolution_rate": 0.80, "max_escalation_rate": 0.35, "max_p95_latency_ms": 2000.0, "max_vendor_error_rate": 0.02})
