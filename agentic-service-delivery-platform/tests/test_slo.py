import pytest

from delivery_platform.slo import SLOTracker


def test_empty_tracker_returns_none():
    tracker = SLOTracker()
    assert tracker.availability("svc") is None
    assert tracker.burn_rate("svc") is None
    assert tracker.latency_p95("svc") is None
    assert tracker.error_budget_remaining("svc") is None
    assert tracker.alerts("svc") == []


def test_availability_and_error_budget():
    tracker = SLOTracker()
    for _ in range(999):
        tracker.record("svc", ok=True, latency_ms=10.0)
    tracker.record("svc", ok=False, latency_ms=900.0)
    assert tracker.availability("svc") == 0.999
    # target 0.999 allows 1 error in 1000; 1 error used it all up.
    assert tracker.error_budget_remaining("svc", 0.999) == pytest.approx(0.0, abs=1e-9)
    assert tracker.burn_rate("svc", 0.999) == pytest.approx(1.0)


def test_burn_rate_above_one_triggers_alert():
    tracker = SLOTracker()
    for _ in range(100):
        tracker.record("svc", ok=True, latency_ms=10.0)
    for _ in range(10):
        tracker.record("svc", ok=False, latency_ms=900.0)
    # 10 errors in 110 samples vs 0.1% allowed -> burn ~91x.
    assert tracker.burn_rate("svc", 0.999) > 2.0
    alerts = tracker.alerts("svc", 0.999)
    assert any("burn rate" in a for a in alerts)
    assert any("availability" in a for a in alerts)


def test_latency_p95():
    tracker = SLOTracker()
    for ms in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 1000.0]:
        tracker.record("svc", ok=True, latency_ms=ms)
    assert tracker.latency_p95("svc") == 90.0


def test_negative_latency_raises():
    tracker = SLOTracker()
    with pytest.raises(ValueError, match="must not be negative"):
        tracker.record("svc", ok=True, latency_ms=-1.0)


def test_summary_shape():
    tracker = SLOTracker()
    for _ in range(10):
        tracker.record("svc", ok=True, latency_ms=25.0)
    summary = tracker.summary("svc", 0.999)
    assert summary["service"] == "svc"
    assert summary["samples"] == 10
    assert summary["availability"] == 1.0
    assert summary["alerts"] == []
