"""Tests for the fraud-detection model validation project."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fraud_validation.data import FEATURES, generate_transactions, train_test_split
from fraud_validation.fairness import max_flag_rate_gap, slice_metrics
from fraud_validation.metrics import (
    calibration_by_decile,
    confusion_matrix_at,
    decile_capture,
    evaluate_model,
    ks_statistic,
    roc_auc,
    tune_threshold,
)
from fraud_validation.models import ChallengerModel, fit_all, predict_all
from fraud_validation.monitoring import drift_report, psi
from fraud_validation.report import SECTION_HEADINGS, build_report


@pytest.fixture(scope="module")
def data():
    return generate_transactions()


@pytest.fixture(scope="module")
def split(data):
    return train_test_split(data)


@pytest.fixture(scope="module")
def fitted(split):
    train, test = split
    models = fit_all(train)
    scores = predict_all(models, test)
    return train, test, models, scores


def test_data_shape_and_columns(data):
    assert len(data) == 20_000
    for col in FEATURES + ["region", "is_fraud"]:
        assert col in data.columns
    assert set(data["is_fraud"].unique()) <= {0, 1}


def test_fraud_rate_near_two_percent(data):
    rate = float(data["is_fraud"].mean())
    assert 0.01 < rate < 0.04, f"fraud rate {rate:.4f} outside expected range"


def test_seeded_reproducibility():
    a = generate_transactions(seed=42)
    b = generate_transactions(seed=42)
    pd.testing.assert_frame_equal(a, b)
    c = generate_transactions(seed=7)
    assert not a.equals(c)


def test_train_test_split_sizes(data):
    train, test = train_test_split(data)
    assert len(train) == 16_000
    assert len(test) == 4_000
    assert len(train) + len(test) == len(data)


def test_champion_auc_beats_benchmark(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    assert roc_auc(y_true, scores["champion"]) > roc_auc(y_true, scores["benchmark"])
    assert roc_auc(y_true, scores["champion"]) > 0.7
    assert roc_auc(y_true, scores["benchmark"]) == pytest.approx(0.5)


def test_ks_in_open_interval(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    ks = ks_statistic(y_true, scores["champion"])
    assert 0.0 < ks < 1.0


def test_confusion_matrix_sums_to_test_size(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    cm = confusion_matrix_at(y_true, scores["champion"], 0.05)
    assert sum(cm.values()) == len(test)


def test_decile_capture_sums_to_one(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    capture = decile_capture(y_true, scores["champion"])
    assert len(capture) == 10
    assert capture["capture_rate"].sum() == pytest.approx(1.0)
    # Riskiest decile captures the most fraud.
    assert capture.loc[0, "capture_rate"] > capture.loc[9, "capture_rate"]


def test_calibration_deciles_cover_zero_to_one(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    cal = calibration_by_decile(y_true, scores["champion"])
    assert len(cal) == 10
    assert cal["mean_predicted"].min() >= 0.0
    assert cal["mean_predicted"].max() <= 1.0
    assert cal["observed_rate"].min() >= 0.0
    assert cal["observed_rate"].max() <= 1.0
    # Observed fraud rises with predicted decile.
    assert cal["observed_rate"].iloc[-1] > cal["observed_rate"].iloc[0]


def test_psi_finite_and_small_for_stable_features(split):
    train, test = split
    drift = drift_report(train, test, FEATURES)
    assert np.isfinite(drift["psi"]).all()
    assert (drift["psi"] < 0.25).all()
    assert drift["psi"].mean() < 0.1


def test_fairness_slices_return_all_regions(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    slices = slice_metrics(y_true, scores["champion"], test["region"], 0.05)
    assert set(slices["segment"]) == {"North", "South", "East", "West"}
    assert len(slices) == 4
    gap = max_flag_rate_gap(slices)
    assert 0.0 <= gap <= 1.0


def test_threshold_tuning_in_open_interval(fitted):
    _, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    threshold = tune_threshold(y_true, scores["champion"])
    assert 0.0 < threshold < 1.0


def test_challenger_fits_and_predicts(split):
    train, test = split
    challenger = ChallengerModel().fit(train)
    scores = challenger.predict(test)
    assert len(scores) == len(test)
    assert np.isfinite(scores).all()
    assert scores.min() >= 0.0 and scores.max() <= 1.0
    y_true = test["is_fraud"].to_numpy()
    assert roc_auc(y_true, scores) > 0.7


def test_report_contains_required_headings(fitted):
    train, test, _, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    threshold = tune_threshold(y_true, scores["champion"])
    results = {
        name: evaluate_model(y_true, score, threshold=threshold)
        for name, score in scores.items()
    }
    drift = drift_report(train, test, FEATURES)
    slices = slice_metrics(y_true, scores["champion"], test["region"], threshold)
    report = build_report(
        results, drift, slices, max_flag_rate_gap(slices),
        len(train), len(test), float(test["is_fraud"].mean()),
    )
    for heading in SECTION_HEADINGS:
        assert heading in report
    # Real numbers appear in the report.
    assert f"{results['champion']['roc_auc']:.4f}" in report
