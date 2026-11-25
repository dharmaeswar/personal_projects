import pytest

from ops.latency_telemetry import latency_summary, percentile, rolling_breach


def test_percentile_basic():
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 95)


def test_summary_no_breach():
    result = latency_summary([4, 5, 6, 5, 7, 8, 5, 6, 9, 5], slo_ms=20)
    assert result["breach"] is False
    assert result["count"] == 10


def test_summary_breach():
    result = latency_summary([4, 5, 6, 5, 7, 8, 5, 6, 42, 5], slo_ms=20)
    assert result["breach"] is True
    assert result["p95_ms"] == 42


def test_rolling_breach_windows():
    samples = [5, 5, 5, 50, 50, 5, 5, 5]
    breaches = rolling_breach(samples, window=4, slo_ms=20)
    assert breaches
    assert all(p95 > 20 for _, p95 in breaches)
