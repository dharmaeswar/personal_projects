"""Tests for the credit-risk analytics module."""

import numpy as np
import pandas as pd

from fraud_validation.credit_risk import (
    SCORE_BAND_LABELS,
    build_credit_features,
    decision_cutoff_analysis,
    generate_credit_applications,
    gini_coefficient,
    roll_rate,
    score_band_performance,
    vintage_analysis,
)


def _apps():
    return generate_credit_applications(n=2000, seed=7)


def test_generation_is_deterministic_and_shaped():
    a = generate_credit_applications(n=500, seed=7)
    b = generate_credit_applications(n=500, seed=7)
    assert a.equals(b)
    assert len(a) == 500
    assert a["bureau_score"].between(300, 850).all()
    assert a["is_bad"].isin([0, 1]).all()
    assert 0.01 < a["is_bad"].mean() < 0.5


def test_credit_features_cover_all_bands():
    feats = build_credit_features(_apps())
    assert set(feats["score_band"].unique()) <= set(SCORE_BAND_LABELS)
    assert feats["utilisation_band"].isin(["low", "medium", "high"]).all()
    assert (feats["dti_proxy"] >= 0).all()
    assert (feats["loan_to_income"] == feats["dti_proxy"]).all()


def test_gini_is_positive_for_bureau_score():
    apps = _apps()
    gini = gini_coefficient(
        apps["is_bad"].to_numpy(), apps["bureau_score"].to_numpy(dtype=float)
    )
    assert 0.0 < gini < 1.0


def test_gini_zero_for_constant_score():
    y = np.array([0, 1, 0, 1, 1, 0])
    assert gini_coefficient(y, np.ones(6)) == 0.0


def test_band_bad_rates_fall_with_score():
    bands = score_band_performance(build_credit_features(_apps()))
    assert len(bands) == 6
    assert bands["n"].sum() == 2000
    # Lowest band must be materially worse than the highest band.
    low = bands.loc[bands["score_band"] == "300-579", "bad_rate"].iloc[0]
    high = bands.loc[bands["score_band"] == "740-850", "bad_rate"].iloc[0]
    assert low > high + 0.05


def test_cutoffs_trade_approval_for_bad_rate():
    cutoffs = decision_cutoff_analysis(_apps())
    assert len(cutoffs) == 4
    # Higher cutoff: fewer approvals, lower bad rate among approved.
    assert cutoffs["approval_rate"].is_monotonic_decreasing
    assert cutoffs["approved_bad_rate"].is_monotonic_decreasing
    assert cutoffs["bad_capture"].is_monotonic_increasing


def test_vintage_covers_all_months_and_sums():
    vintages = vintage_analysis(_apps())
    assert len(vintages) == 12
    assert vintages["n"].sum() == 2000
    assert vintages["bad_rate"].between(0, 1).all()


def test_roll_rate_is_bounded():
    rolls = roll_rate(_apps())
    assert 0.0 <= rolls["roll_30_to_90"] <= 1.0
    assert rolls["n_30dpd"] > 0
    assert rolls["dpd_90_rate"] <= rolls["dpd_30_rate"]
