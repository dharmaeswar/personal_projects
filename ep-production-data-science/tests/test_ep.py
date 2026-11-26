import numpy as np
import pandas as pd
import pytest

from ep_data.cleaning import clean_production, validate_dictionary
from ep_data.data import generate_dataset, generate_monthly_production, generate_wells
from ep_data.decline import arps_rate, estimate_eur, fit_decline
from ep_data.features import FEATURE_COLUMNS, add_features
from ep_data.forecast import backtest


def test_generate_wells_shape():
    wells = generate_wells(10, seed=1)
    assert len(wells) == 10
    assert wells["api_number"].is_unique
    assert (wells["lateral_ft"] > 0).all()
    assert (wells["proppant_lbs"] > 0).all()


def test_monthly_production_declines():
    wells = generate_wells(5, seed=2)
    monthly = generate_monthly_production(wells, n_months=12, seed=2)
    assert len(monthly) == 60
    first = monthly[monthly["api_number"] == monthly["api_number"].iloc[0]]
    # Oil declines on average from the first 3 months to the last 3.
    assert first["oil_bbl"].iloc[:3].mean() > first["oil_bbl"].iloc[-3:].mean()
    assert (monthly["oil_bbl"] > 0).all()


def test_cleaning_removes_duplicates_negatives_and_nulls():
    raw = generate_dataset(n_wells=10, n_months=12, seed=3, with_issues=True)
    assert raw.duplicated(subset=["api_number", "month_index"]).sum() > 0
    assert (raw["oil_bbl"] < 0).any()
    assert raw["gas_mcf"].isna().any()
    clean, log = clean_production(raw)
    assert log["duplicates_dropped"] > 0
    assert log["negative_rows_dropped"] > 0
    assert log["nulls_remaining"] == 0
    assert validate_dictionary(clean) == []
    assert clean.duplicated(subset=["api_number", "month_index"]).sum() == 0


def test_features_no_lookahead_and_ranges():
    raw = generate_dataset(n_wells=5, n_months=12, seed=4, with_issues=False)
    clean, _ = clean_production(raw)
    feat = add_features(clean)
    for col in FEATURE_COLUMNS:
        assert col in feat.columns
    assert ((feat["water_cut"] >= 0) & (feat["water_cut"] <= 1)).all()
    assert (feat["gor_mcf_bbl"] >= 0).all()
    # Cumulative oil is non-decreasing within each well.
    for _, w in feat.groupby("api_number"):
        assert w["cum_oil_bbl"].is_monotonic_increasing
    # First month: lag filled with own rate, decline 0.
    first = feat[feat["month_index"] == 0]
    assert (first["decline_rate"] == 0).all()


def test_arps_rate_exponential_limit():
    t = np.array([0.0, 1.0, 2.0])
    exp = arps_rate(100.0, 0.1, 0.0, t)
    assert np.allclose(exp, 100.0 * np.exp(-0.1 * t))
    hyp = arps_rate(100.0, 0.1, 1.0, t)
    assert hyp[0] == 100.0 and hyp[1] < 100.0 and hyp[2] < hyp[1]


def test_fit_decline_recovers_known_params():
    t = np.arange(24, dtype=float)
    q = arps_rate(800.0, 0.08, 1.2, t)
    fit = fit_decline(t, q)
    assert abs(fit["qi"] - 800.0) / 800.0 < 0.05
    assert abs(fit["di"] - 0.08) < 0.02
    assert abs(fit["b"] - 1.2) < 0.15
    assert fit["r2_log"] > 0.99


def test_fit_decline_needs_enough_data():
    with pytest.raises(ValueError):
        fit_decline(np.arange(3), np.array([100.0, 90.0, 80.0]))


def test_eur_positive_and_bounded():
    fit = {"qi": 800.0, "di": 0.08, "b": 1.2}
    eur = estimate_eur(fit, 24)
    assert eur["eur_bbl"] > 0
    assert 0 < eur["months_to_limit"] <= 360


def test_backtest_beats_persistence_baseline():
    raw = generate_dataset(n_wells=40, n_months=36, seed=42, with_issues=True)
    clean, _ = clean_production(raw)
    feat = add_features(clean)
    bt = backtest(feat)
    assert bt["n_train"] > 0 and bt["n_test"] > 0
    assert bt["rmse_bbl"] > 0
    assert bt["beats_baseline"] is True
    assert bt["mape"] < 0.30
