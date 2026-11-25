"""Tests for anomaly detection over streaming telemetry."""

from event_intel.anomaly import (correlate, mad_detect, rule_detect,
                                 zscore_detect)

# Flat baseline of 20, then a spike to 90 at window 10, back to ~20.
COUNTS = [20, 21, 19, 20, 22, 20, 19, 21, 20, 20, 90, 21, 20, 19, 20]


def test_zscore_detects_spike_not_baseline():
    result = zscore_detect("sensor-a", COUNTS)
    assert len(result.anomalies) == 1
    assert result.anomalies[0].window_start == 10.0
    assert result.anomalies[0].value == 90
    assert result.anomalies[0].severity == "critical"


def test_zscore_ignores_flat_series():
    result = zscore_detect("sensor-a", [20] * 15)
    assert result.anomalies == []


def test_zscore_needs_history():
    result = zscore_detect("sensor-a", [20, 21])
    assert result.anomalies == []


def test_mad_detects_spike():
    result = mad_detect("sensor-a", COUNTS)
    assert any(a.window_start == 10.0 for a in result.anomalies)
    assert result.anomalies[0].detector == "mad"


def test_rule_ceiling_flags_breach():
    result = rule_detect("sensor-a", COUNTS, max_count=50)
    assert len(result.anomalies) == 1
    assert result.anomalies[0].detector == "rule-ceiling"
    assert result.anomalies[0].severity == "critical"


def test_rule_growth_flags_doubling():
    result = rule_detect("sensor-a", [10, 11, 10, 25], max_count=100)
    assert len(result.anomalies) == 1
    assert result.anomalies[0].detector == "rule-growth"


def test_correlate_groups_same_window_sources():
    a = zscore_detect("sensor-a", COUNTS)
    b = zscore_detect("sensor-b", COUNTS)
    signals = correlate([a, b])
    assert len(signals) == 1
    assert signals[0]["sources"] == ["sensor-a", "sensor-b"]
    assert signals[0]["window_start"] == 10.0
    assert signals[0]["max_severity"] == "critical"


def test_correlate_ignores_single_source():
    a = zscore_detect("sensor-a", COUNTS)
    assert correlate([a]) == []
