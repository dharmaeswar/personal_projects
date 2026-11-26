"""Tests for rates, rolling trends, z-scores and emerging risks."""

from safetyint.data import generate_events, monthly_counts
from safetyint.trends import (
    baseline_zscores,
    emerging_risks,
    monthly_rates,
    rolling_rate,
    trend_slope,
)


def _rates():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    return monthly_rates(counts, exposure), exposure


def test_monthly_rate_uses_flights_denominator():
    counts = {"2024-01": {c: 10 for c in ("unstable-approach",)}}
    from safetyint.data import CATEGORIES, MonthFlights

    full = {
        "2024-01": {c: (10 if c == "unstable-approach" else 0) for c in CATEGORIES}
    }
    rates = monthly_rates(full, [MonthFlights("2024-01", 100000)])
    assert rates["2024-01"]["unstable-approach"] == 1.0


def test_rolling_rate_partial_windows():
    assert rolling_rate([1.0, 2.0, 3.0, 4.0], window=3) == [1.0, 1.5, 2.0, 3.0]


def test_trend_slope_rising_and_flat():
    assert trend_slope([1.0, 2.0, 3.0, 4.0]) == 1.0
    assert trend_slope([5.0, 5.0, 5.0]) == 0.0
    assert trend_slope([3.0]) == 0.0


def test_zscores_baseline_months_near_zero_mean():
    rates, _ = _rates()
    zscores = baseline_zscores(rates)
    baseline = [zscores["bird-strike"][m] for m in sorted(rates)[:12]]
    assert abs(sum(baseline) / len(baseline)) < 0.5


def test_emerging_risks_finds_planted_drift():
    rates, _ = _rates()
    hits = emerging_risks(rates)
    categories = [h["category"] for h in hits]
    assert "unstable-approach" in categories
    hit = next(h for h in hits if h["category"] == "unstable-approach")
    assert hit["max_recent_z"] >= 2.0
    assert hit["recent_rate"] > hit["baseline_rate"]


def test_emerging_risks_empty_without_drift():
    events, exposure = generate_events(drift_factor=1.0)
    counts = monthly_counts(events, exposure)
    rates = monthly_rates(counts, exposure)
    # With no planted drift, unstable-approach must not be flagged.
    hits = emerging_risks(rates)
    assert "unstable-approach" not in [h["category"] for h in hits]
