"""Tests for ops/alert_tuning.py (demo project)."""

from ops.alert_tuning import (
    evaluate_threshold,
    generate_synthetic_series,
    recommend_threshold,
    sweep_thresholds,
)


def _sample(minute, value, incident=False):
    return {"minute": minute, "value": value, "incident": incident}


def _hand_series():
    # 20 minutes: quiet baseline, one 4-minute incident, one lone spike.
    samples = [_sample(m, 0.01) for m in range(20)]
    for m in range(8, 12):
        samples[m] = _sample(m, 0.25, incident=True)
    samples[16] = _sample(16, 0.07)
    return samples


def test_low_threshold_detects_incident_but_spike_is_false_positive():
    result = evaluate_threshold(_hand_series(), 0.05, min_consecutive=1)
    assert result["incidents_total"] == 1
    assert result["incidents_detected"] == 1
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1


def test_consecutive_minutes_suppresses_one_minute_spike():
    result = evaluate_threshold(_hand_series(), 0.05, min_consecutive=2)
    assert result["incidents_detected"] == 1
    assert result["false_positives"] == 0


def test_high_threshold_misses_incident():
    result = evaluate_threshold(_hand_series(), 0.40, min_consecutive=1)
    assert result["alerts"] == 0
    assert result["incidents_missed"] == 1


def test_sweep_returns_one_result_per_candidate():
    results = sweep_thresholds(_hand_series(), [0.05, 0.10, 0.20])
    assert [r["threshold"] for r in results] == [0.05, 0.10, 0.20]


def test_recommend_prefers_no_miss_then_fewest_false_positives():
    best = recommend_threshold(
        _hand_series(), [0.05, 0.10, 0.40], min_consecutive=1
    )
    assert best["threshold"] == 0.10
    assert best["incidents_missed"] == 0
    assert best["false_positives"] == 0
    assert "reason" in best


def test_synthetic_series_is_deterministic_and_labelled():
    first = generate_synthetic_series()
    second = generate_synthetic_series()
    assert first == second
    assert sum(1 for s in first if s["incident"]) == 25
    result = evaluate_threshold(first, 0.10, min_consecutive=2)
    assert result["incidents_total"] == 2
    assert result["incidents_detected"] == 2
    assert result["false_positives"] == 0
