"""Tests for the transaction-risk scoring module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fraud_validation.data import generate_transactions, train_test_split
from fraud_validation.metrics import evaluate_model
from fraud_validation.models import fit_all, predict_all
from fraud_validation.transaction_risk import (
    RISK_FEATURES,
    add_event_days,
    build_transaction_features,
    build_transaction_risk_section,
    delayed_label_evaluation,
    latency_quality_tradeoff,
    pattern_shift_report,
    regression_check,
)


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


def test_features_added_and_bounded(data):
    feats = build_transaction_features(data)
    for col in RISK_FEATURES:
        assert col in feats.columns
    assert feats["night"].isin([0, 1]).all()
    assert feats["new_device"].isin([0, 1]).all()
    assert feats["cross_border_cnp"].isin([0, 1]).all()
    assert (feats["velocity_ratio"] >= 0).all()
    assert np.isfinite(feats["amount_zscore"]).all()
    # Night flag matches the hour rule; new-device flag matches the age rule.
    assert (feats["night"] == ((data["hour"] < 5) | (data["hour"] >= 23)).astype(int)).all()
    assert (feats["new_device"] == (data["device_age_days"] < 30).astype(int)).all()
    # Interaction flag is 1 only for cross-border card-not-present rows.
    assert (feats["cross_border_cnp"] == (data["cross_border"] * (1 - data["card_present"]))).all()


def test_features_deterministic(data):
    a = build_transaction_features(data)
    b = build_transaction_features(data)
    pd.testing.assert_frame_equal(a, b)


def test_event_days_seeded_and_in_range(data):
    a = add_event_days(data)
    b = add_event_days(data)
    pd.testing.assert_frame_equal(a, b)
    assert a["event_day"].min() >= 0
    assert a["event_day"].max() < 60


def test_delayed_labels_counts_and_bias(fitted):
    _, test, _, scores = fitted
    dated = add_event_days(test)
    result = delayed_label_evaluation(
        test["is_fraud"].to_numpy(), scores["champion"],
        dated["event_day"].to_numpy(), latest_day=59, maturation_days=30,
    )
    assert result["n_matured"] + result["n_pending"] == len(test)
    assert 0 < result["n_matured"] < len(test)
    assert 0 < result["n_pending"] < len(test)
    assert 0.5 < result["matured_roc_auc"] <= 1.0
    # Naive evaluation (pending treated as legitimate) understates the model.
    assert result["naive_roc_auc"] <= result["matured_roc_auc"]
    # Everything matured: no pending rows.
    full = delayed_label_evaluation(
        test["is_fraud"].to_numpy(), scores["champion"],
        dated["event_day"].to_numpy(), latest_day=59, maturation_days=0,
    )
    assert full["n_pending"] == 0
    assert full["n_matured"] == len(test)


def test_pattern_shift_flags_injected_shift():
    # Synthetic frame: fraud concentrates in "online_retail" in the recent
    # period, while the baseline period is flat across categories.
    rng = np.random.default_rng(0)
    rows = []
    for period in ("baseline", "recent"):
        for cat in ("grocery", "online_retail"):
            n = 200
            fraud_rate = 0.30 if (period == "recent" and cat == "online_retail") else 0.02
            rows.append(pd.DataFrame({
                "merchant_category": [cat] * n,
                "period": [period] * n,
                "is_fraud": rng.binomial(1, fraud_rate, size=n),
            }))
    frame = pd.concat(rows, ignore_index=True)
    scores = np.where(frame["is_fraud"] == 1, 0.9, 0.1)
    shifts = pattern_shift_report(
        frame, frame["is_fraud"].to_numpy(), scores, threshold=0.5
    )
    assert set(shifts["segment"]) == {"grocery", "online_retail"}
    online = shifts[shifts["segment"] == "online_retail"].iloc[0]
    assert bool(online["flagged"]) is True
    assert online["change_pp"] > 5.0
    grocery = shifts[shifts["segment"] == "grocery"].iloc[0]
    assert bool(grocery["flagged"]) is False


def test_pattern_shift_empty_when_no_periods(data):
    frame = data.head(100).copy()
    frame["period"] = "baseline"
    scores = np.full(100, 0.1)
    shifts = pattern_shift_report(
        frame, frame["is_fraud"].to_numpy(), scores, threshold=0.5
    )
    assert len(shifts) == 0


def test_latency_tradeoff_table(fitted):
    _, test, models, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    table = latency_quality_tradeoff(models, test, y_true, threshold=0.05, sample_n=50)
    assert set(table["model"]) == {"champion", "challenger", "benchmark"}
    assert (table["mean_ms_per_txn"] > 0).all()
    assert (table["p99_ms_per_txn"] >= table["mean_ms_per_txn"]).all()
    # Champion and challenger beat chance; the constant benchmark is 0.5.
    assert table.loc[table["model"] == "champion", "roc_auc"].iloc[0] > 0.7
    assert table.loc[table["model"] == "challenger", "roc_auc"].iloc[0] > 0.7
    assert table.loc[table["model"] == "benchmark", "roc_auc"].iloc[0] == pytest.approx(0.5)
    assert (table["fraud_capture"] >= 0).all() and (table["fraud_capture"] <= 1).all()
    # The linear champion scores faster than the gradient-boosting challenger.
    champion_ms = table.loc[table["model"] == "champion", "mean_ms_per_txn"].iloc[0]
    challenger_ms = table.loc[table["model"] == "challenger", "mean_ms_per_txn"].iloc[0]
    assert champion_ms < challenger_ms


def test_regression_check_flags_drop():
    baseline = {"roc_auc": 0.85, "precision": 0.40, "recall": 0.60, "f1": 0.48}
    # Small drops within tolerance: PASS overall.
    current_ok = {"roc_auc": 0.84, "precision": 0.39, "recall": 0.58, "f1": 0.47}
    ok = regression_check(baseline, current_ok)
    assert ok.attrs["overall"] == "PASS"
    assert (ok["status"] == "PASS").all()
    # Recall drops 0.10, beyond the 0.05 tolerance: REGRESSION.
    current_bad = {"roc_auc": 0.84, "precision": 0.39, "recall": 0.50, "f1": 0.47}
    bad = regression_check(baseline, current_bad)
    assert bad.attrs["overall"] == "REGRESSION"
    assert bad.loc[bad["metric"] == "recall", "status"].iloc[0] == "REGRESSION"
    assert bad.loc[bad["metric"] == "roc_auc", "status"].iloc[0] == "PASS"


def test_transaction_risk_section_text(fitted):
    _, test, models, scores = fitted
    y_true = test["is_fraud"].to_numpy()
    dated = add_event_days(test)
    delayed = delayed_label_evaluation(
        y_true, scores["champion"], dated["event_day"].to_numpy(), latest_day=59
    )
    dated["period"] = np.where(dated["event_day"] < 30, "baseline", "recent")
    shifts = pattern_shift_report(dated, y_true, scores["champion"], threshold=0.05)
    tradeoff = latency_quality_tradeoff(models, test, y_true, threshold=0.05, sample_n=20)
    base = evaluate_model(y_true, scores["champion"], threshold=0.05)
    base_metrics = {k: base[k] for k in ("roc_auc", "precision", "recall", "f1")}
    regression = regression_check(base_metrics, base_metrics)
    section = build_transaction_risk_section(
        delayed, shifts, tradeoff, regression, n_features=len(RISK_FEATURES)
    )
    assert "9. Transaction Risk Scoring" in section
    assert "Delayed labels" in section
    assert "Adversarial pattern checks" in section
    assert "Model quality vs latency" in section
    assert "Model-regression monitoring" in section
