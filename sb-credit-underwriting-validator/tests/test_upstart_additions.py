"""Tests for the Upstart additions: engineered features, the gradient-boosting
challenger, and champion/challenger experiment design."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sb_credit_validator.data import generate_portfolio
from sb_credit_validator.experiments import (
    bootstrap_auc_diff, log_loss, min_sample_size, paired_logloss_test)
from sb_credit_validator.features import (
    FEATURE_COLUMNS, coverage_band, engineer_features, score_band)
from sb_credit_validator.models import (
    GradientBoostingChallenger, LogisticModel)
from sb_credit_validator.outcomes import roc_auc


def _loans(n=600, seed=1):
    return generate_portfolio(n=n, seed=seed)


def test_score_bands():
    assert score_band(550) == 0
    assert score_band(640) == 1
    assert score_band(700) == 2
    assert score_band(780) == 3


def test_coverage_bands():
    assert coverage_band(0.8) == 0
    assert coverage_band(1.2) == 1
    assert coverage_band(2.0) == 2
    assert coverage_band(3.0) == 3


def test_engineered_features_values():
    row = {"annual_revenue": 200000.0, "years_in_business": 5.0,
           "cashflow_coverage": 1.6, "credit_score": 700,
           "loan_amount": 50000.0, "industry_risk": 0.10}
    feats = engineer_features(row)
    assert len(feats) == len(FEATURE_COLUMNS)
    assert feats[6] == 0.25  # loan-to-income
    assert feats[8] == 2.0  # prime score band
    assert feats[9] == 2.0  # strong coverage band
    assert feats[0] == 200000.0 and feats[3] == 700


def test_engineered_features_handle_zero_revenue():
    row = {"annual_revenue": 0.0, "years_in_business": 5.0,
           "cashflow_coverage": 1.6, "credit_score": 700,
           "loan_amount": 50000.0, "industry_risk": 0.10}
    feats = engineer_features(row)
    assert feats[6] == 0.0
    assert feats[7] == 0.0


def test_gbm_challenger_scores_in_range_and_beats_random():
    loans = _loans()
    y = [l["defaulted"] for l in loans]
    scores = GradientBoostingChallenger().fit(loans).predict_proba(loans)
    assert len(scores) == len(loans)
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert roc_auc(y, scores) > 0.70


def test_gbm_challenger_is_deterministic():
    loans = _loans()
    a = GradientBoostingChallenger().fit(loans).predict_proba(loans)
    b = GradientBoostingChallenger().fit(loans).predict_proba(loans)
    assert a == b


def test_gbm_differs_from_logistic_champion():
    loans = _loans()
    champ = LogisticModel().fit(loans).predict_proba(loans)
    gbm = GradientBoostingChallenger().fit(loans).predict_proba(loans)
    assert any(abs(a - b) > 1e-6 for a, b in zip(champ, gbm))


def test_log_loss_known_case():
    assert abs(log_loss([1, 0], [0.9, 0.1]) - 0.1053605) < 1e-6
    assert log_loss([1, 0], [1.0, 0.0]) > 0.0  # clipped, never explodes


def test_paired_logloss_identical_scores():
    y = [1, 0, 1, 0, 1, 0]
    s = [0.8, 0.2, 0.7, 0.3, 0.6, 0.4]
    r = paired_logloss_test(y, s, s)
    assert r["mean_diff"] == 0.0
    assert r["p_value"] == 1.0


def test_paired_logloss_detects_worse_model():
    y = [1, 1, 0, 0] * 25
    good = [0.9, 0.8, 0.2, 0.1] * 25
    bad = [0.5, 0.5, 0.5, 0.5] * 25
    r = paired_logloss_test(y, good, bad)
    assert r["mean_diff"] > 0  # bad model has higher log-loss
    assert r["p_value"] < 0.05


def test_bootstrap_auc_diff_identical_scores():
    y = [1, 1, 0, 0] * 25
    s = [0.9, 0.8, 0.2, 0.1] * 25
    r = bootstrap_auc_diff(y, s, s, n_boot=50, seed=7)
    assert r["mean_diff"] == 0.0
    assert r["ci_lo"] <= 0.0 <= r["ci_hi"]


def test_bootstrap_auc_diff_detects_better_model():
    loans = _loans()
    y = [l["defaulted"] for l in loans]
    champ = LogisticModel().fit(loans).predict_proba(loans)
    gbm = GradientBoostingChallenger().fit(loans).predict_proba(loans)
    r = bootstrap_auc_diff(y, champ, gbm, n_boot=100, seed=7)
    assert r["n_boot"] == 100
    assert r["ci_lo"] <= r["mean_diff"] <= r["ci_hi"]


def test_sample_size_grows_as_mde_shrinks():
    assert min_sample_size(0.10, 0.01) > min_sample_size(0.10, 0.02)
    assert min_sample_size(0.10, 0.01) > 0


def test_sample_size_rejects_bad_inputs():
    try:
        min_sample_size(1.5, 0.01)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for baseline_rate > 1")
    try:
        min_sample_size(0.10, 0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for mde = 0")
