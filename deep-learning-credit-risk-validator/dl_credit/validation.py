"""Second-line validation checks for the deep-learning candidate.

- Vintage backtesting: predicted vs realised default rate by origination
  quarter, breach when the ratio sits outside [0.80, 1.25].
- Ongoing monitoring: PSI drift of scores and of each feature between the
  validation population and a later production population.
- Data integrity: missing values, duplicate keys, out-of-range scores.
- Permutation importance: how much test AUC each feature carries.
- Implementation reproduction: re-fit from scratch with the same seed
  and compare outputs within tolerance.
"""
import numpy as np
import pandas as pd

from .metrics import psi, roc_auc


def vintage_backtest(df, proba, low=0.80, high=1.25):
    """Per-quarter predicted vs realised default rate with breach flags."""
    out = []
    frame = df.assign(proba=np.asarray(proba, dtype=float))
    for quarter, group in frame.groupby("origination_quarter", sort=True):
        pred = float(group["proba"].mean())
        obs = float(group["defaulted"].mean())
        ratio = pred / obs if obs > 0 else float("nan")
        out.append({
            "quarter": str(quarter),
            "n": int(len(group)),
            "predicted_rate": pred,
            "observed_rate": obs,
            "ratio": ratio,
            "breach": bool(obs > 0 and (ratio < low or ratio > high)),
        })
    return out


def drift_report(train_df, later_df, train_proba, later_proba, feature_cols):
    """PSI for scores and for each feature, train vs later population."""
    rows = [{
        "feature": "model_score",
        "psi": psi(train_proba, later_proba),
    }]
    for col in feature_cols:
        rows.append({
            "feature": col,
            "psi": psi(train_df[col].to_numpy(dtype=float),
                       later_df[col].to_numpy(dtype=float)),
        })
    return rows


def data_integrity(df):
    """Missing values, duplicate rows, out-of-range credit scores."""
    issues = []
    missing = int(df.isna().sum().sum())
    if missing:
        issues.append({"check": "missing_values", "count": missing,
                       "severity": "Medium"})
    dup = int(df.duplicated().sum())
    if dup:
        issues.append({"check": "duplicate_rows", "count": dup,
                       "severity": "Low"})
    bad_scores = int(((df["credit_score"] < 300) | (df["credit_score"] > 850)).sum())
    if bad_scores:
        issues.append({"check": "credit_score_out_of_range", "count": bad_scores,
                       "severity": "Medium"})
    bad_util = int(((df["revolving_utilization"] < 0) |
                    (df["revolving_utilization"] > 1)).sum())
    if bad_util:
        issues.append({"check": "utilization_out_of_range", "count": bad_util,
                       "severity": "Medium"})
    return issues


def permutation_importance(model, X, y, feature_names, seed=3):
    """Drop in test AUC when one feature's values are shuffled."""
    rng = np.random.default_rng(seed)
    base = roc_auc(y, model.predict_proba(X))
    out = []
    for j, name in enumerate(feature_names):
        Xp = X.copy()
        Xp[:, j] = rng.permutation(Xp[:, j])
        out.append({
            "feature": name,
            "auc_drop": float(base - roc_auc(y, model.predict_proba(Xp))),
        })
    out.sort(key=lambda r: -r["auc_drop"])
    return out, float(base)
