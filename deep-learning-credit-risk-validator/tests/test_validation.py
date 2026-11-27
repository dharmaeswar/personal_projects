import numpy as np

from dl_credit.challengers import BaseRateModel, LogisticRegression
from dl_credit.data import feature_matrix, generate, standardize, time_split
from dl_credit.validation import (data_integrity, drift_report,
                                  permutation_importance, vintage_backtest)
from dl_credit.report import build_report


def _small_split():
    df = generate(n=800)
    train, val, test = time_split(df)
    Xtr, names = feature_matrix(train)
    Xte, _ = feature_matrix(test)
    Xtr_s, mean, std = standardize(Xtr, Xtr)
    Xte_s = (Xte - mean) / std
    return df, train, test, Xtr_s, Xte_s, names


def test_logistic_regression_beats_base_rate():
    df, train, test, Xtr_s, Xte_s, _ = _small_split()
    ytr = train["defaulted"].to_numpy()
    yte = test["defaulted"].to_numpy()
    logreg = LogisticRegression(lr=0.1, epochs=300).fit(Xtr_s, ytr)
    from dl_credit.metrics import roc_auc
    assert roc_auc(yte, logreg.predict_proba(Xte_s)) > 0.6
    base = BaseRateModel().fit(Xtr_s, ytr)
    assert np.allclose(base.predict_proba(Xte_s), ytr.mean())


def test_vintage_backtest_shape_and_breach_flag():
    df, train, test, Xtr_s, Xte_s, _ = _small_split()
    rng = np.random.default_rng(0)
    proba = rng.random(len(test))
    rows = vintage_backtest(test, proba)
    assert len(rows) == 2  # 2025Q3, 2025Q4
    assert all("breach" in r and "ratio" in r for r in rows)
    # Absurd predictions must breach.
    rows_bad = vintage_backtest(test, np.full(len(test), 0.99))
    assert any(r["breach"] for r in rows_bad)


def test_data_integrity_clean_and_dirty():
    df = generate(n=200)
    assert data_integrity(df) == []
    dirty = df.copy()
    dirty.loc[dirty.index[0], "credit_score"] = 999
    dirty.loc[dirty.index[1], "credit_score"] = None
    issues = data_integrity(dirty)
    kinds = {i["check"] for i in issues}
    assert "credit_score_out_of_range" in kinds
    assert "missing_values" in kinds


def test_drift_report_flags_shift():
    df = generate(n=600)
    train, val, test = time_split(df)
    from dl_credit.data import NUMERIC_FEATURES
    shifted = val.copy()
    shifted["credit_score"] = shifted["credit_score"] - 200
    rows = drift_report(train, shifted, np.full(len(train), 0.2),
                        np.full(len(val), 0.2), NUMERIC_FEATURES)
    by_name = {r["feature"]: r["psi"] for r in rows}
    assert by_name["credit_score"] > 0.25
    assert by_name["model_score"] < 1e-9


def test_permutation_importance_ranks_real_signal_first():
    df, train, test, Xtr_s, Xte_s, names = _small_split()
    ytr = train["defaulted"].to_numpy()
    yte = test["defaulted"].to_numpy()
    logreg = LogisticRegression(lr=0.1, epochs=300).fit(Xtr_s, ytr)
    imp, base = permutation_importance(logreg, Xte_s, yte, names)
    assert len(imp) == len(names)
    assert imp[0]["feature"] in ("credit_score", "revolving_utilization",
                                 "debt_to_income", "delinquencies_12m")


def test_build_report_verdict_logic():
    good = {"roc_auc": 0.85, "max_calibration_gap": 0.02}
    chal = {"roc_auc": 0.80}
    bench = {"roc_auc": 0.5}
    backtest = [{"quarter": "2025Q3", "breach": False},
                {"quarter": "2025Q4", "breach": False}]
    drift = [{"feature": "model_score", "psi": 0.01}]
    report = build_report(good, chal, bench, backtest, drift, [], [], 100, 50)
    assert report["verdict"] == "PASS"
    bad = dict(good, roc_auc=0.70)
    report2 = build_report(bad, chal, bench, backtest, drift, [], [], 100, 50)
    assert report2["verdict"] == "FAIL"
    assert any(f["id"] == "F-01" for f in report2["findings"])
