from fintech_agents.observability import (
    CostTracker, Metrics, StructuredLogger, Tracer)


def test_structured_log_carries_trace_and_fields():
    logger = StructuredLogger()
    line = logger.log("info", "close started", trace_id="t-1",
                      span_id="s-1", month="2026-11")
    assert line["level"] == "info"
    assert line["trace_id"] == "t-1"
    assert line["span_id"] == "s-1"
    assert line["month"] == "2026-11"
    assert len(logger.lines) == 1


def test_tracer_spans_share_trace_and_record_duration():
    tracer = Tracer()
    root = tracer.start_span("close_cycle", trace_id="trace-0001")
    child = tracer.start_span("reconcile", trace_id="trace-0001",
                              parent=root)
    assert child.parent_span_id == root.span_id
    assert child.trace_id == root.trace_id
    tracer.end_span(child)
    tracer.end_span(root)
    assert child.duration_ms is not None
    assert child.duration_ms >= 0
    assert root.duration_ms >= child.duration_ms


def test_cost_tracker_totals_tokens_and_spend():
    tracker = CostTracker()
    tracker.record("close-planner", 800, 200, 0.005)
    tracker.record("close-planner", 400, 100, 0.005)
    assert tracker.total_tokens == 1500
    assert tracker.total_cost_usd == 0.0075


def test_metrics_p95_still_works():
    metrics = Metrics()
    for ms in (10, 20, 30, 40, 50):
        metrics.record_latency("close", ms)
    assert metrics.p95_ms("close") == 50
    assert metrics.p95_ms("missing") == 0.0
