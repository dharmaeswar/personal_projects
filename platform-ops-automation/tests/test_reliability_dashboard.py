"""Tests for ops/reliability_dashboard.py (demo project)."""

import pytest

from ops.reliability_dashboard import (
    evaluate_alerts,
    generate_synthetic_signals,
    summarize,
)


def _signals(n_ok, n_err, latency_ok=0.05, latency_err=0.6, service="web"):
    signals = [
        {"service": service, "ok": True, "latency": latency_ok}
        for _ in range(n_ok)
    ]
    signals += [
        {"service": service, "ok": False, "latency": latency_err}
        for _ in range(n_err)
    ]
    return signals


def test_summary_all_healthy():
    summary = summarize(_signals(100, 0))
    assert summary["total"] == 100
    assert summary["errors"] == 0
    assert summary["availability"] == 100.0
    assert summary["error_rate"] == 0.0
    assert summary["p95_latency"] == 0.05
    assert summary["error_budget_remaining"] == pytest.approx(0.1)
    assert evaluate_alerts(summary) == []


def test_summary_with_errors_fires_alerts():
    summary = summarize(_signals(90, 10))
    assert summary["availability"] == 90.0
    assert summary["error_rate"] == 0.1
    assert summary["error_budget_remaining"] < 0
    rules = {a["rule"] for a in evaluate_alerts(summary)}
    assert "availability-below-slo" in rules
    assert "error-rate-high" in rules
    severities = {a["rule"]: a["severity"] for a in evaluate_alerts(summary)}
    assert severities["availability-below-slo"] == "critical"


def test_p95_latency_threshold():
    summary = summarize(_signals(95, 5, latency_ok=0.05, latency_err=0.9))
    assert summary["p95_latency"] == 0.05
    assert not any(
        a["rule"] == "latency-p95-high" for a in evaluate_alerts(summary)
    )
    slow = _signals(0, 0) + [
        {"service": "web", "ok": True, "latency": 0.8} for _ in range(100)
    ]
    slow_summary = summarize(slow)
    assert slow_summary["p95_latency"] == 0.8
    assert any(
        a["rule"] == "latency-p95-high"
        for a in evaluate_alerts(slow_summary)
    )


def test_by_service_breakdown():
    signals = _signals(90, 10, service="teller") + _signals(
        100, 0, service="account-opening"
    )
    summary = summarize(signals)
    assert summary["by_service"]["teller"]["availability"] == 90.0
    assert summary["by_service"]["account-opening"]["availability"] == 100.0
    assert summary["by_service"]["teller"]["errors"] == 10


def test_empty_signals():
    summary = summarize([])
    assert summary["total"] == 0
    assert summary["availability"] == 100.0
    assert summary["p95_latency"] is None
    assert evaluate_alerts(summary) == []


def test_synthetic_demo_signals():
    signals = generate_synthetic_signals()
    summary = summarize(signals)
    assert summary["total"] == 800
    assert summary["errors"] > 0
    assert summary["by_service"]["teller"]["errors"] > 0
    assert summary["by_service"]["account-opening"]["errors"] == 0
