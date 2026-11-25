"""Tests for the small-business credit underwriting validator."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sb_credit_validator.data import generate_portfolio
from sb_credit_validator.models import LogisticModel
from sb_credit_validator.outcomes import (
    roc_auc, ks_statistic, gini, decile_capture, calibration_by_decile,
    confusion_at_threshold)
from sb_credit_validator.validation import (
    vintage_backtest, psi, score_drift, data_completeness_checks,
    reproduction_check)
from sb_credit_validator.report import (
    build_findings, recommend_rating, render_report)


def _loans(n=600, seed=1):
    return generate_portfolio(n=n, seed=seed)


def test_data_has_expected_fields_and_defaults():
    loans = _loans()
    assert len(loans) == 600
    assert all(set(l) >= {"loan_id", "credit_score", "defaulted"} for l in loans)
    assert 0 < sum(l["defaulted"] for l in loans) < 600
    assert len({l["loan_id"] for l in loans}) == 600


def test_data_is_deterministic():
    a = generate_portfolio(n=100, seed=5)
    b = generate_portfolio(n=100, seed=5)
    assert a == b


def test_drift_shifts_scores_down():
    base = generate_portfolio(n=500, seed=3)
    drifted = generate_portfolio(n=500, seed=3, drift=True)
    assert sum(l["credit_score"] for l in drifted) < sum(l["credit_score"] for l in base)


def test_champion_fits_and_scores_in_range():
    loans = _loans()
    model = LogisticModel().fit(loans)
    scores = model.predict_proba(loans)
    assert len(scores) == len(loans)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_champion_beats_random():
    loans = _loans()
    y = [l["defaulted"] for l in loans]
    scores = LogisticModel().fit(loans).predict_proba(loans)
    assert roc_auc(y, scores) > 0.70


def test_challenger_interactions_change_scores():
    loans = _loans()
    base = LogisticModel(interactions=False).fit(loans).predict_proba(loans)
    chal = LogisticModel(interactions=True).fit(loans).predict_proba(loans)
    assert any(abs(a - b) > 1e-6 for a, b in zip(base, chal))


def test_auc_perfect_and_random():
    assert roc_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert roc_auc([1, 0], [0.5, 0.5]) == 0.5
    assert roc_auc([1, 1], [0.9, 0.8]) == 0.5


def test_ks_known_case():
    assert ks_statistic([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert ks_statistic([1, 0], [0.5, 0.5]) == 0.0


def test_gini_from_auc():
    assert abs(gini([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) - 1.0) < 1e-9


def test_decile_capture_sums_to_one():
    loans = _loans()
    y = [l["defaulted"] for l in loans]
    scores = LogisticModel().fit(loans).predict_proba(loans)
    deciles = decile_capture(y, scores)
    assert len(deciles) == 10
    assert abs(sum(deciles) - 1.0) < 0.01
    assert deciles[0] >= deciles[-1]


def test_calibration_rows_match_deciles():
    loans = _loans()
    y = [l["defaulted"] for l in loans]
    scores = LogisticModel().fit(loans).predict_proba(loans)
    cal = calibration_by_decile(y, scores)
    assert len(cal) == 10
    assert all(0.0 <= p <= 1.0 and 0.0 <= o <= 1.0 for p, o in cal)


def test_confusion_counts_add_up():
    cm = confusion_at_threshold([1, 1, 0, 0], [0.9, 0.4, 0.6, 0.1])
    assert cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"] == 4
    assert cm["tp"] == 1 and cm["fp"] == 1


def test_vintage_backtest_covers_all_quarters():
    loans = _loans()
    scores = LogisticModel().fit(loans).predict_proba(loans)
    bt = vintage_backtest(loans, scores)
    assert len(bt) == 6
    assert all(v["n"] > 0 for v in bt.values())
    assert all(0.0 < v["ratio"] < 5.0 for v in bt.values())


def test_psi_identical_is_zero():
    s = [0.1, 0.2, 0.3, 0.4, 0.5] * 20
    assert psi(s, s) == 0.0


def test_psi_grows_with_shift():
    base = [0.2] * 100 + [0.4] * 100
    shifted = [0.7] * 100 + [0.9] * 100
    assert psi(base, shifted) > 0.25


def test_score_drift_sign():
    assert score_drift([0.2, 0.2], [0.3, 0.3]) == 0.5
    assert score_drift([0.4, 0.4], [0.2, 0.2]) == -0.5


def test_data_checks_clean_portfolio():
    assert data_completeness_checks(_loans()) == []


def test_data_checks_catch_bad_scores():
    loans = _loans()
    loans[0]["credit_score"] = 999
    issues = data_completeness_checks(loans)
    assert any("credit scores" in i for i in issues)


def test_data_checks_catch_duplicates():
    loans = _loans()
    loans[1]["loan_id"] = loans[0]["loan_id"]
    issues = data_completeness_checks(loans)
    assert any("duplicate" in i for i in issues)


def test_reproduction_check_passes_on_refit():
    loans = _loans()
    a = LogisticModel().fit(loans).predict_proba(loans)
    b = LogisticModel().fit(loans).predict_proba(loans)
    r = reproduction_check(a, b)
    assert r["reproduced"] is True
    assert r["max_abs_diff"] == 0.0


def test_reproduction_check_fails_on_shift():
    r = reproduction_check([0.1, 0.2], [0.1, 0.5])
    assert r["reproduced"] is False


def test_findings_flag_weak_auc():
    outcomes = {"auc": 0.60, "challenger_auc": 0.62}
    f = build_findings(outcomes, {}, 0.0, 0.0, [], True, False)
    assert any(s == "High" and "AUC" in t for s, t in f)


def test_findings_flag_backtest_breach():
    outcomes = {"auc": 0.80, "challenger_auc": 0.80}
    bt = {"2024-Q1": {"breach": True}}
    f = build_findings(outcomes, bt, 0.0, 0.0, [], True, False)
    assert any("Backtest" in t for _, t in f)


def test_rating_follows_worst_finding():
    assert recommend_rating([("High", "x")]) == "High"
    assert recommend_rating([("Medium", "x")]) == "Medium"
    assert recommend_rating([("Low", "x")]) == "Low"


def test_report_renders_all_sections():
    results = {
        "n": 600, "auc": 0.78, "ks": 0.45, "gini": 0.56,
        "challenger_auc": 0.79, "challenger_ks": 0.46,
        "deciles": [0.3] + [0.07] * 8 + [0.04],
        "confusion": {"precision": 0.6, "recall": 0.2, "f1": 0.3},
        "backtest": {"2024-Q1": {"n": 100, "predicted": 0.1, "observed": 0.09,
                                 "ratio": 1.11, "breach": False}},
        "psi": 0.05, "drift": 0.02, "data_issues": [],
        "reproduced": True, "max_diff": 0.0,
        "findings": [("Low", "No material findings")],
        "rating": "Low", "owner_rating": "Medium", "verdict": "PASS",
    }
    text = render_report(results)
    for section in ["CONCEPTUAL SOUNDNESS", "OUTCOMES ANALYSIS", "BACKTESTING",
                    "MONITORING", "DATA INTEGRITY", "FINDINGS", "RISK RATING"]:
        assert section in text
