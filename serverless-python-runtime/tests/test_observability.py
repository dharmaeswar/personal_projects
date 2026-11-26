import json

from runtime.observability import Metrics, log_event, percentile, span


def test_percentile_empty():
    assert percentile([], 95) == 0.0


def test_percentile_values():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(samples, 50) == 3.0
    assert percentile(samples, 95) == 5.0


def test_metrics_summary(capsys):
    metrics = Metrics()
    metrics.record(10.0, cold=True, ok=True)
    metrics.record(20.0, cold=False, ok=True)
    metrics.record(30.0, cold=False, ok=False)
    summary = metrics.summary()
    assert summary == {
        "invocations": 3,
        "cold_starts": 1,
        "warm_invocations": 2,
        "failures": 1,
        "p50_ms": 20.0,
        "p95_ms": 30.0,
        "max_ms": 30.0,
    }


def test_log_event_is_json_line(capsys):
    line = log_event("info", "bundle built", total_bytes=123)
    parsed = json.loads(line)
    assert parsed["level"] == "info"
    assert parsed["message"] == "bundle built"
    assert parsed["total_bytes"] == 123


def test_span_records_duration():
    with span("work") as info:
        assert info["name"] == "work"
    assert info["duration_ms"] >= 0
