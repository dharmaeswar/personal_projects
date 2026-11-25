"""Tests for the production serving monitor."""

import pytest

from inference_optimizer.serving_monitor import (
    LatencySLO,
    ServingSnapshot,
    check_latency,
    compare_outputs,
    investigate_discrepancy,
)


SLO = LatencySLO(p50_ms=20.0, p95_ms=40.0, p99_ms=80.0)


def test_latency_passes_when_inside_slo():
    report = check_latency([12.0, 15.0, 18.0, 22.0, 30.0], SLO)
    assert report.passes is True
    assert report.breaches == ()
    assert report.samples == 5
    assert report.p50_ms == 18.0
    assert report.max_ms == 30.0


def test_latency_flags_p95_breach():
    latencies = [10.0] * 18 + [100.0, 100.0]
    report = check_latency(latencies, SLO)
    assert report.passes is False
    assert "p95" in report.breaches
    assert "p50" not in report.breaches


def test_latency_rejects_empty_and_non_positive():
    with pytest.raises(ValueError):
        check_latency([], SLO)
    with pytest.raises(ValueError):
        check_latency([10.0, 0.0], SLO)


def test_slo_must_be_ordered():
    with pytest.raises(ValueError):
        LatencySLO(p50_ms=50.0, p95_ms=40.0, p99_ms=80.0)


def test_tail_stall_bottleneck():
    # p99 far above p95: occasional stalls, not a slow steady path.
    report = check_latency([10.0] * 98 + [90.0, 200.0],
                           LatencySLO(p50_ms=20.0, p95_ms=40.0, p99_ms=300.0))
    assert report.bottleneck == "tail-stall"


def test_systematic_bottleneck():
    report = check_latency([35.0, 36.0, 37.0, 38.0, 39.0], SLO)
    assert report.bottleneck == "systematic"


def test_compare_outputs_passes_within_tolerance():
    ref = [1.0, 2.0, 3.0, 4.0]
    prod = [1.001, 1.999, 3.002, 4.0]
    result = compare_outputs(ref, prod, tolerance=0.01)
    assert result.passes is True
    assert result.over_tolerance == 0
    assert result.max_abs_diff == pytest.approx(0.002, abs=1e-6)
    assert result.worst_index == 2


def test_compare_outputs_fails_over_tolerance():
    result = compare_outputs([1.0, 2.0, 3.0], [1.0, 2.5, 3.0], tolerance=0.1)
    assert result.passes is False
    assert result.over_tolerance == 1
    assert result.fraction_over_tolerance == pytest.approx(1 / 3)


def test_compare_outputs_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        compare_outputs([1.0, 2.0], [1.0], tolerance=0.1)


def test_investigate_passing_comparison_needs_no_action():
    result = compare_outputs([1.0, 2.0], [1.001, 2.0], tolerance=0.01)
    findings = investigate_discrepancy(result)
    assert len(findings) == 1
    assert findings[0].cause == "no discrepancy"


def test_investigate_preprocessing_mismatch_ranked_first():
    result = compare_outputs([1.0, 2.0, 3.0], [1.0, 9.0, 3.0], tolerance=0.1)
    findings = investigate_discrepancy(result, preprocessing_changed=True,
                                       dtype_changed=True)
    assert findings[0].cause.startswith("data preprocessing")
    assert findings[0].likelihood == "likely"
    assert all(f.check for f in findings)


def test_investigate_quantization_drift_when_diff_is_small():
    result = compare_outputs([1.0, 2.0, 3.0, 4.0],
                             [1.05, 2.05, 3.05, 4.05], tolerance=0.01)
    findings = investigate_discrepancy(result, dtype_changed=True)
    assert findings[0].cause.startswith("quantization drift")


def test_investigate_unexplained_drift_when_nothing_changed():
    result = compare_outputs([1.0, 2.0], [5.0, 2.0], tolerance=0.1)
    findings = investigate_discrepancy(result)
    assert findings[0].cause == "unexplained drift"


def test_serving_snapshot_healthy():
    latency = check_latency([12.0, 15.0, 18.0], SLO)
    snap = ServingSnapshot(gpu_memory_used_gb=40.0, gpu_memory_total_gb=80.0,
                           gpu_utilization=0.7, throughput_tokens_per_sec=1200.0,
                           error_rate=0.001, latency=latency)
    assert snap.health()["verdict"] == "healthy"
    assert snap.memory_pressure == pytest.approx(0.5)


def test_serving_snapshot_degraded_on_slo_breach():
    latency = check_latency([10.0] * 18 + [100.0, 100.0], SLO)
    snap = ServingSnapshot(gpu_memory_used_gb=40.0, gpu_memory_total_gb=80.0,
                           gpu_utilization=0.7, throughput_tokens_per_sec=1200.0,
                           error_rate=0.001, latency=latency)
    health = snap.health()
    assert health["verdict"] == "degraded"
    assert any("SLO" in r for r in health["reasons"])


def test_serving_snapshot_critical_on_high_error_rate():
    latency = check_latency([12.0, 15.0, 18.0], SLO)
    snap = ServingSnapshot(gpu_memory_used_gb=40.0, gpu_memory_total_gb=80.0,
                           gpu_utilization=0.7, throughput_tokens_per_sec=1200.0,
                           error_rate=0.08, latency=latency)
    assert snap.health()["verdict"] == "critical"
