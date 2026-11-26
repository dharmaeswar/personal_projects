"""Tests for risk scoring and the SMS-style risk matrix."""

from safetyint.data import CATEGORIES, generate_events, monthly_counts
from safetyint.risk import likelihood_band, risk_matrix_cell, risk_scores
from safetyint.trends import monthly_rates


def test_likelihood_bands():
    assert likelihood_band(1.0) == "low"
    assert likelihood_band(4.0) == "medium"
    assert likelihood_band(9.0) == "high"


def test_risk_matrix_cells():
    assert risk_matrix_cell("high", 5) == "HIGH — priority review"
    assert risk_matrix_cell("medium", 4) == "MEDIUM-HIGH — monitor closely"
    assert risk_matrix_cell("high", 3) == "MEDIUM-HIGH — monitor closely"
    assert risk_matrix_cell("low", 2) == "LOW — routine monitoring"
    assert risk_matrix_cell("medium", 2) == "MEDIUM — scheduled review"


def test_risk_scores_cover_all_categories_sorted():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    rates = monthly_rates(counts, exposure)
    scores = risk_scores(rates)
    assert [s["category"] for s in scores] == sorted(
        [s["category"] for s in scores],
        key=lambda c: next(
            s["score"] for s in scores if s["category"] == c
        ),
        reverse=True,
    )
    assert {s["category"] for s in scores} == set(CATEGORIES)


def test_risk_scores_positive_and_trend_labelled():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    rates = monthly_rates(counts, exposure)
    scores = risk_scores(rates)
    assert all(s["score"] > 0 for s in scores)
    assert all(s["trend"] in ("rising", "falling", "flat") for s in scores)
    drift = next(s for s in scores if s["category"] == "unstable-approach")
    assert drift["trend"] == "rising"


def test_severity_weight_drives_score():
    # Same rate, higher severity weight must score higher.
    rates = {
        f"2024-{m:02d}": {c: 5.0 for c in CATEGORIES} for m in range(1, 13)
    }
    scores = risk_scores(rates)
    top = scores[0]["category"]
    assert top == "runway-excursion-precursor"  # severity weight 5
