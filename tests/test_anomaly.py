"""Tests for IQR anomaly detection."""

from safetyint.anomaly import find_anomalies
from safetyint.data import CATEGORIES, generate_events, monthly_counts
from safetyint.trends import monthly_rates


def test_anomaly_flags_spike_above_fence():
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    rates = {
        m: {c: 5.0 for c in CATEGORIES} for m in months
    }
    rates["2024-12"]["bird-strike"] = 50.0
    hits = find_anomalies(rates)
    assert any(
        h["month"] == "2024-12" and h["category"] == "bird-strike"
        for h in hits
    )


def test_anomaly_ignores_flat_series():
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    rates = {m: {c: 5.0 for c in CATEGORIES} for m in months}
    assert find_anomalies(rates) == []


def test_anomaly_hit_carries_fence_and_z():
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    rates = {m: {c: 5.0 for c in CATEGORIES} for m in months}
    rates["2024-12"]["tcas-ra"] = 40.0
    hits = find_anomalies(rates)
    hit = next(h for h in hits if h["category"] == "tcas-ra")
    assert hit["rate"] > hit["upper_fence"]
    assert hit["z"] > 2.0


def test_generated_data_anomalies_are_plausible():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    rates = monthly_rates(counts, exposure)
    hits = find_anomalies(rates)
    # The planted drift should surface as anomalies, not as noise spam.
    assert 0 < len(hits) <= 12
    assert any(h["category"] == "unstable-approach" for h in hits)
