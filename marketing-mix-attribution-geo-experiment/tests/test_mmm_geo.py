"""Tests for the MMM, attribution and geo-experiment modules."""

import numpy as np

from mmm_geo.attribution import compare_attribution, shapley_credit
from mmm_geo.data_gen import (CHANNELS, TRUE_BETA, generate_geo,
                              generate_journeys, generate_weekly,
                              geometric_adstock, hill)
from mmm_geo.geo_experiment import analyze_geo
from mmm_geo.mmm import build_features, fit_mmm, recommend_reallocation


def test_weekly_shape_and_columns():
    df = generate_weekly()
    assert len(df) == 104
    for ch in CHANNELS:
        assert f"spend_{ch}" in df.columns
        assert (df[f"spend_{ch}"] >= 0).all()
    assert (df["sales"] > 0).all()


def test_adstock_decays_and_preserves_total_order():
    x = np.array([100.0, 0.0, 0.0, 0.0])
    out = geometric_adstock(x, theta=0.5)
    assert out[0] == 100.0
    assert out[1] == 50.0 and out[2] == 25.0 and out[3] == 12.5


def test_hill_saturation_is_monotone_and_bounded():
    x = np.array([0.0, 10.0, 50.0, 100.0, 1000.0])
    y = hill(x, ec=50.0)
    assert y[0] == 0.0
    assert np.all(np.diff(y) > 0)
    assert y[-1] < 1.0 and y[-1] > 0.9


def test_mmm_fit_recovers_channel_order():
    df = generate_weekly()
    result = fit_mmm(df)
    assert result["r2_train"] > 0.8
    assert result["mape_holdout"] < 0.10
    coefs = {r["channel"]: r["coef_per_1k"] for r in result["channels"]}
    # Email and paid search are the strongest true drivers; display weakest.
    assert coefs["email"] > coefs["display"]
    assert coefs["paid_search"] > coefs["display"]
    assert all(r["roi"] > 0 for r in result["channels"])


def test_mmm_shares_sum_to_one():
    result = fit_mmm(generate_weekly())
    total = sum(r["share_of_incremental"] for r in result["channels"])
    assert abs(total - 1.0) < 0.01


def test_reallocation_moves_spend_to_highest_roi():
    result = fit_mmm(generate_weekly())
    rec = recommend_reallocation(result)
    assert rec["from_channel"] != rec["to_channel"]
    assert rec["moved_spend_k"] > 0
    assert rec["expected_incremental_gain"] > 0


def test_features_have_no_missing_values():
    X, y = build_features(generate_weekly())
    assert not X.isna().any().any()
    assert len(y) == 104


def test_geo_design_is_balanced():
    df = generate_geo()
    assert df["treated"].sum() == 10 * 20
    assert set(df["period"].unique()) == {"pre", "post"}
    assert df["geo"].nunique() == 40


def test_geo_did_recovers_true_lift():
    # Pausing paid social removes ~45 signups/DMA/week; DiD should be near -45.
    res = analyze_geo(generate_geo())
    assert res["did_per_dma_week"] < -20
    assert abs(res["did_per_dma_week"] + 45.0) < 20
    assert res["did_p_value"] < 0.05
    assert res["recommendation"] == "KEEP RUNNING"


def test_geo_cuped_agrees_with_did():
    res = analyze_geo(generate_geo())
    assert abs(res["cuped_per_dma_week"] - res["did_per_dma_week"]) < 15


def test_attribution_shares_sum_to_one():
    journeys = generate_journeys(n=5000)
    out = compare_attribution(journeys)
    for rule, shares in out.items():
        assert abs(sum(shares.values()) - 1.0) < 0.02, rule


def test_last_touch_overcredits_paid_search_vs_shapley():
    journeys = generate_journeys(n=5000)
    out = compare_attribution(journeys)
    # Last-touch under-credits the assisting channels: Shapley gives email
    # and organic search materially more credit than last-touch does, while
    # paid search (the strongest closer) keeps a large Shapley share.
    assert out["shapley"]["email"] > out["last_touch"]["email"]
    assert out["shapley"]["organic_search"] > out["last_touch"]["organic_search"]
    assert out["shapley"]["paid_search"] > out["last_touch"]["paid_search"]


def test_shapley_is_deterministic():
    a = shapley_credit(n_per_subset=1000)
    b = shapley_credit(n_per_subset=1000)
    assert a == b
