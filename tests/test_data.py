"""Tests for synthetic safety data generation."""

from safetyint.data import (
    CATEGORIES,
    generate_events,
    month_labels,
    monthly_counts,
)


def test_month_labels_roll_over_year():
    assert month_labels(2024, 11, 4) == [
        "2024-11",
        "2024-12",
        "2025-01",
        "2025-02",
    ]


def test_generation_is_repeatable_with_same_seed():
    events_a, exposure_a = generate_events()
    events_b, exposure_b = generate_events()
    assert events_a == events_b
    assert exposure_a == exposure_b


def test_generation_covers_24_months_and_all_categories():
    events, exposure = generate_events()
    assert len(exposure) == 24
    assert {e.category for e in events} == set(CATEGORIES)
    assert all(e.flights > 0 for e in events)


def test_monthly_counts_sum_matches_event_total():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    total = sum(sum(month.values()) for month in counts.values())
    assert total == len(events)


def test_drift_raises_drift_category_late_in_series():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    months = sorted(counts)
    early = sum(counts[m]["unstable-approach"] for m in months[:12])
    late = sum(counts[m]["unstable-approach"] for m in months[18:])
    # 6 late months vs 12 early months, with a 1.8x drift: late total
    # should exceed half the early total even after noise.
    assert late > early / 2


def test_no_drift_when_factor_is_one():
    events, exposure = generate_events(drift_factor=1.0)
    counts = monthly_counts(events, exposure)
    months = sorted(counts)
    early = sum(counts[m]["unstable-approach"] for m in months[:12])
    late = sum(counts[m]["unstable-approach"] for m in months[18:])
    assert late <= early  # no planted rise without the drift factor
