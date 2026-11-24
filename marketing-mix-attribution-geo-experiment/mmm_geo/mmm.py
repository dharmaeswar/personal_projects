"""Marketing mix model: adstock + Hill saturation, fit by Ridge regression.

Pipeline per channel: raw weekly spend -> geometric adstock -> Hill
saturation (scaled by the half-saturation point so coefficients stay on a
per-$1k-spend scale) -> Ridge regression on sales with seasonality, holiday
and promo as controls. The last 12 weeks are held out for validation.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_percentage_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data_gen import CHANNELS, TRUE_EC, geometric_adstock, hill

HOLDOUT_WEEKS = 12


def transform_spend(spend, ec):
    """Adstock then saturate, scaled by ec so the unit is ~$1k of spend."""
    return hill(geometric_adstock(spend), ec) * ec


def build_features(df):
    """Return the design matrix (transformed spend + controls) and sales."""
    cols = {}
    for ch in CHANNELS:
        cols[ch] = transform_spend(df[f"spend_{ch}"].to_numpy(), TRUE_EC[ch])
    X = pd.DataFrame(cols)
    X["seasonality"] = df["seasonality"].to_numpy()
    X["holiday"] = df["holiday"].to_numpy()
    X["promo"] = df["promo"].to_numpy()
    return X, df["sales"].to_numpy()


def fit_mmm(df):
    """Fit the MMM; return fitted model, metrics and per-channel results."""
    X, y = build_features(df)
    X_train, X_test = X.iloc[:-HOLDOUT_WEEKS], X.iloc[-HOLDOUT_WEEKS:]
    y_train, y_test = y[:-HOLDOUT_WEEKS], y[-HOLDOUT_WEEKS:]
    # Standardise before Ridge: raw features live on very different scales
    # (transformed spend ~tens, seasonality ~hundreds), and unscaled Ridge
    # shrinks them unevenly and can flip small-channel coefficients.
    pipe = make_pipeline(StandardScaler(),
                         RidgeCV(alphas=np.logspace(-2, 2, 20)))
    pipe.fit(X_train, y_train)
    scaler = pipe.named_steps["standardscaler"]
    ridge = pipe.named_steps["ridgecv"]
    # Recover coefficients on the original (per-$1k) scale.
    coef_orig = ridge.coef_ / scaler.scale_
    intercept_orig = float(ridge.intercept_
                           - np.sum(ridge.coef_ * scaler.mean_
                                    / scaler.scale_))
    pred_test = pipe.predict(X_test)
    pred_train = pipe.predict(X_train)

    coefs = dict(zip(X.columns, coef_orig))
    alpha = float(ridge.alpha_)
    rows = []
    for ch in CHANNELS:
        spend_total = float(df[f"spend_{ch}"].sum())
        contrib = float(coefs[ch] * X[ch].sum())
        rows.append({
            "channel": ch,
            "coef_per_1k": round(float(coefs[ch]), 3),
            "total_spend_k": round(spend_total, 1),
            "total_contribution": round(contrib, 1),
            "roi": round(contrib / spend_total, 3) if spend_total else 0.0,
            "share_of_incremental": 0.0,  # filled below
        })
    total_contrib = sum(r["total_contribution"] for r in rows)
    for r in rows:
        r["share_of_incremental"] = round(
            r["total_contribution"] / total_contrib, 3) if total_contrib else 0.0
    return {
        "model": pipe,
        "intercept": intercept_orig,
        "alpha": alpha,
        "r2_train": round(float(r2_score(y_train, pred_train)), 3),
        "mape_holdout": round(float(mean_absolute_percentage_error(
            y_test, pred_test)), 4),
        "channels": rows,
        "total_incremental": round(total_contrib, 1),
    }


def recommend_reallocation(result, shift_fraction=0.10):
    """Shift `shift_fraction` of spend from the lowest-ROI to highest-ROI channel.

    Returns the expected incremental-sales change under the fitted linear
    model (a planning estimate, not a causal guarantee).
    """
    rows = sorted(result["channels"], key=lambda r: r["roi"])
    worst, best = rows[0], rows[-1]
    move = worst["total_spend_k"] * shift_fraction
    gain = move * (best["roi"] - worst["roi"])
    return {
        "from_channel": worst["channel"],
        "to_channel": best["channel"],
        "moved_spend_k": round(move, 1),
        "expected_incremental_gain": round(float(gain), 1),
    }
