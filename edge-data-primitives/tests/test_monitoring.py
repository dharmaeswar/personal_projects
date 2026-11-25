from edgeprimitives.monitoring import (
    AlertRule,
    Metrics,
    analyze_logs,
    evaluate_alerts,
)


def test_metrics_percentiles_and_error_rate():
    m = Metrics()
    for ms in [10, 20, 30, 40, 50]:
        m.record("read", ms)
    m.record("read", 500, ok=False)
    assert m.error_rate("read") == 1 / 6
    assert m.percentile("read", 50) == 40  # index int(0.50 * 6) = 3rd of sorted samples
    assert m.percentile("read", 95) == 500
    assert m.percentile("missing", 95) is None


def test_alert_rule_fires_and_clears():
    rule = AlertRule("slow", "read.p95_ms", 100.0)
    assert rule.check(150.0) is not None
    assert rule.check(50.0) is None


def test_evaluate_alerts_uses_live_metrics():
    m = Metrics()
    for _ in range(9):
        m.record("write", 10)
    m.record("write", 10, ok=False)
    rules = [AlertRule("errors", "write.error_rate", 0.05)]
    fired = evaluate_alerts(m, rules)
    assert len(fired) == 1 and "errors" in fired[0]
    assert evaluate_alerts(m, [AlertRule("ok", "write.error_rate", 0.5)]) == []


def test_evaluate_alerts_with_extra_values():
    m = Metrics()
    rules = [AlertRule("backlog", "queue.depth", 0.0)]
    assert evaluate_alerts(m, rules, {"queue.depth": 5.0}) != []
    assert evaluate_alerts(m, rules, {"queue.depth": 0.0}) == []


def test_analyze_logs_counts_errors_and_slowest():
    lines = [
        "2026-11-25T10:00:00Z INFO read 12.5ms",
        "2026-11-25T10:00:01Z ERROR write 210.0ms code=TIMEOUT slow write",
        "2026-11-25T10:00:02Z ERROR write 95.0ms code=TIMEOUT again",
        "2026-11-25T10:00:03Z WARN read 300.0ms",
        "not a log line",
    ]
    out = analyze_logs(lines)
    assert out["total_lines"] == 4
    assert out["malformed_lines"] == 1
    assert out["errors_by_code"] == {"TIMEOUT": 2}
    assert out["slowest_ms_by_operation"] == {"read": 300.0, "write": 210.0}
