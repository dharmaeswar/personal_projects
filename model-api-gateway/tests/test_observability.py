from gateway.observability import Metrics, percentile


def test_percentile_nearest_rank():
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 95) is None


def test_summary_reports_p50_p95_and_error_rate():
    metrics = Metrics()
    for latency in (100, 120, 140, 160, 900):
        metrics.observe("m1", latency)
    metrics.observe("m1", 200, error=True)
    stats = metrics.summary("m1")
    assert stats["requests"] == 6
    assert stats["errors"] == 1
    assert abs(stats["error_rate"] - 1 / 6) < 1e-9
    assert stats["p50_ms"] == 140
    assert stats["p95_ms"] == 900


def test_slo_ok_when_within_budgets():
    metrics = Metrics()
    for _ in range(10):
        metrics.observe("m1", 100)
    result = metrics.evaluate_slo("m1")
    assert result["ok"] is True and result["alerts"] == []


def test_slo_alerts_on_latency_and_error_breaches():
    metrics = Metrics()
    for _ in range(9):
        metrics.observe("m1", 800)
    metrics.observe("m1", 800, error=True)
    result = metrics.evaluate_slo("m1")
    assert result["ok"] is False
    assert any("p95_latency_breach" in a for a in result["alerts"])
    assert any("error_rate_breach" in a for a in result["alerts"])


def test_prometheus_text_lists_models():
    metrics = Metrics()
    metrics.observe("m1", 100)
    text = metrics.prometheus_text()
    assert 'gateway_requests_total{model="m1"} 1' in text
    assert 'gateway_latency_p95_ms{model="m1"} 100.0' in text
