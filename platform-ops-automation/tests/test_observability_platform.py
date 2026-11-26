"""Tests for ops/observability_platform.py (demo project, synthetic data)."""

import pytest

from ops.observability_platform import (
    correlate_incident,
    dashboard_summary,
    detect_anomalies,
    rank_root_causes,
    route_alert,
    summarize_series,
    trace_timeline,
)


def _spans():
    return [
        {"trace_id": "t1", "span_id": "s1", "parent_span_id": None,
         "service": "web", "operation": "GET /checkout", "duration_ms": 120,
         "status": "ok", "start_ms": 1000},
        {"trace_id": "t1", "span_id": "s2", "parent_span_id": "s1",
         "service": "payments", "operation": "charge", "duration_ms": 950,
         "status": "error", "start_ms": 1050},
        {"trace_id": "t1", "span_id": "s3", "parent_span_id": "s2",
         "service": "payments-db", "operation": "INSERT charge", "duration_ms": 900,
         "status": "error", "start_ms": 1060},
    ]


def test_correlate_incident_joins_spans_logs_metrics():
    logs = [
        {"trace_id": "t1", "timestamp_ms": 1100, "level": "ERROR",
         "message": "charge failed: timeout"},
        {"trace_id": "other", "timestamp_ms": 1100, "level": "INFO",
         "message": "unrelated"},
    ]
    metrics = [
        {"timestamp_ms": 900, "name": "error_rate", "value": 0.01},
        {"timestamp_ms": 1500, "name": "error_rate", "value": 0.4},
        {"timestamp_ms": 5000, "name": "error_rate", "value": 0.01},
    ]
    view = correlate_incident(_spans(), logs, metrics)
    assert view["trace_ids"] == ["t1"]
    assert view["error_count"] == 2
    assert view["log_count"] == 1
    assert view["logs"][0]["message"] == "charge failed: timeout"
    assert len(view["metrics_in_window"]) == 1
    assert view["metrics_in_window"][0]["timestamp_ms"] == 1500
    assert view["slowest_span"]["service"] == "payments"


def test_correlate_incident_empty_spans():
    view = correlate_incident([], [], [])
    assert view["trace_ids"] == []
    assert view["error_count"] == 0
    assert view["slowest_span"] is None


def test_trace_timeline_depths():
    timeline = trace_timeline(_spans())
    depths = {span["span_id"]: d for d, span in timeline}
    assert depths == {"s1": 0, "s2": 1, "s3": 2}
    assert [s["span_id"] for _, s in timeline] == ["s1", "s2", "s3"]


def _series():
    # 30 steady minutes at ~10, then a spike to 80 at minute 30.
    samples = [{"minute": i, "value": 10.0 + (i % 3)} for i in range(30)]
    samples.append({"minute": 30, "value": 80.0})
    samples.append({"minute": 31, "value": 11.0})
    return samples


def test_detect_anomalies_flags_spike_only():
    anomalies = detect_anomalies(_series())
    assert [a["minute"] for a in anomalies] == [30]
    assert anomalies[0]["z_score"] >= 3.0


def test_detect_anomalies_flat_series_has_none():
    flat = [{"minute": i, "value": 10.0} for i in range(40)]
    assert detect_anomalies(flat) == []


def test_summarize_series():
    summary = summarize_series([{"minute": i, "value": float(i)} for i in range(1, 101)])
    assert summary["count"] == 100
    assert summary["mean"] == pytest.approx(50.5)
    assert summary["min"] == 1.0
    assert summary["max"] == 100.0
    assert summary["p95"] == 95.0


def test_summarize_series_empty():
    assert summarize_series([])["count"] == 0


def _rows(service, operation, n_ok, n_err, ok_ms=50, err_ms=800):
    rows = [{"service": service, "operation": operation, "ok": True,
             "latency_ms": ok_ms} for _ in range(n_ok)]
    rows += [{"service": service, "operation": operation, "ok": False,
              "latency_ms": err_ms} for _ in range(n_err)]
    return rows


def test_rank_root_causes_puts_failing_service_first():
    baseline = _rows("web", "GET /", 100, 0) + _rows("payments", "charge", 100, 0)
    incident = _rows("web", "GET /", 99, 1) + _rows("payments", "charge", 60, 40)
    ranked = rank_root_causes(baseline, incident)
    assert ranked[0]["service"] == "payments"
    assert ranked[0]["incident_error_rate"] == pytest.approx(0.4)
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_root_causes_healthy_incident_scores_zero():
    baseline = _rows("web", "GET /", 100, 0)
    incident = _rows("web", "GET /", 100, 0)
    assert rank_root_causes(baseline, incident)[0]["score"] == 0.0


def test_route_alert_pages_on_high_error_rate():
    anomaly = {"minute": 30, "value": 80.0, "z_score": 12.0}
    routed = route_alert(anomaly, error_rate=0.08, services_affected=1)
    assert routed["severity"] == "critical"
    assert routed["action"] == "page"
    assert routed["channel"] == "on-call:primary"


def test_route_alert_tickets_on_moderate_deviation():
    anomaly = {"minute": 30, "value": 80.0, "z_score": 4.5}
    routed = route_alert(anomaly, error_rate=0.005, services_affected=1)
    assert routed["severity"] == "warning"
    assert routed["action"] == "ticket"


def test_route_alert_logs_isolated_small_deviation():
    anomaly = {"minute": 30, "value": 80.0, "z_score": 3.1}
    routed = route_alert(anomaly, error_rate=0.001, services_affected=1)
    assert routed["severity"] == "info"
    assert routed["action"] == "log"


def test_dashboard_summary_worst_first():
    signals = (
        [{"service": "web", "ok": True, "latency_ms": 40} for _ in range(100)]
        + [{"service": "db", "ok": True, "latency_ms": 60} for _ in range(90)]
        + [{"service": "db", "ok": False, "latency_ms": 900} for _ in range(10)]
    )
    rows = dashboard_summary(signals)
    assert rows[0]["service"] == "db"
    assert rows[0]["availability"] == 90.0
    assert rows[1]["service"] == "web"
    assert rows[1]["availability"] == 100.0
