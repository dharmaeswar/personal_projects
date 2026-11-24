"""Demand forecasting: Holt-Winters (statsmodels) and Ridge regression (scikit-learn).

Both models are explainable: Holt-Winters exposes level/trend/seasonal components,
Ridge exposes feature coefficients. Holdout MAPE is reported for each so the two
can be compared honestly instead of picking a winner by eye.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def smape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Symmetric MAPE: bounded in [0, 2], safe when actual demand is near zero."""
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    denom = np.abs(actual) + np.abs(predicted)
    terms = np.where(denom > 0, 2.0 * np.abs(actual - predicted) / np.where(denom > 0, denom, 1.0), 0.0)
    return float(np.mean(terms))


def _series_for(history: pd.DataFrame, style: str, region: str) -> pd.Series:
    sub = history[(history["style"] == style) & (history["region"] == region)]
    return sub.sort_values("week")["demand"].reset_index(drop=True).astype(float)


def holt_winters_forecast(series: pd.Series, horizon: int = 4,
                          seasonal_periods: int = 13) -> tuple[np.ndarray, float]:
    """Fit Holt-Winters on all but the last `horizon` weeks; return forecast + holdout sMAPE.

    Quarterly seasonality (13 weeks) is used: a 52-week seasonal cycle would need
    two full cycles in the training window, which a 104-week history cannot give
    once a holdout is held back.
    """
    train, holdout = series.iloc[:-horizon], series.iloc[-horizon:]
    model = ExponentialSmoothing(
        train, trend="add", seasonal="add",
        seasonal_periods=seasonal_periods, initialization_method="estimated",
    ).fit(optimized=True)
    fitted_holdout = model.forecast(horizon)
    err = smape(holdout.to_numpy(), fitted_holdout.to_numpy())
    full = ExponentialSmoothing(
        series, trend="add", seasonal="add",
        seasonal_periods=seasonal_periods, initialization_method="estimated",
    ).fit(optimized=True)
    # Demand cannot be negative; clip the forecast at zero.
    return np.maximum(np.asarray(full.forecast(horizon), dtype=float), 0.0), err


def _ridge_features(series: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Lag 1/2/4/52, linear trend and annual seasonality features."""
    df = pd.DataFrame({"y": series})
    for lag in (1, 2, 4, 52):
        df[f"lag_{lag}"] = df["y"].shift(lag)
    df["trend"] = np.arange(len(df), dtype=float)
    df["sin52"] = np.sin(2 * np.pi * df["trend"] / 52.0)
    df["cos52"] = np.cos(2 * np.pi * df["trend"] / 52.0)
    df = df.dropna().reset_index(drop=True)
    return df.drop(columns=["y"]), df["y"]


def ridge_forecast(series: pd.Series, horizon: int = 4) -> tuple[np.ndarray, float, dict]:
    """Ridge regression on lag/trend/seasonality features; returns forecast, holdout sMAPE, coefficients."""
    X, y = _ridge_features(series)
    X_train, y_train = X.iloc[:-horizon], y.iloc[:-horizon]
    X_hold, y_hold = X.iloc[-horizon:], y.iloc[-horizon:]
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    err = smape(y_hold.to_numpy(), model.predict(X_hold))

    # Refit on all data, then roll the forecast forward one week at a time.
    model.fit(X, y)
    history = list(series)
    preds: list[float] = []
    for step in range(horizon):
        extended = pd.Series(history + preds)
        feats, _ = _ridge_features(extended)
        row = feats.iloc[[-1]]
        preds.append(max(0.0, float(model.predict(row)[0])))
    coefs = dict(zip(X.columns, (round(float(c), 3) for c in model.coef_)))
    return np.asarray(preds), err, coefs


def forecast_all(history: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    """Forecast every style-region; one row per style-region with both models' output."""
    rows = []
    for style in sorted(history["style"].unique()):
        for region in sorted(history["region"].unique()):
            series = _series_for(history, style, region)
            hw_fc, hw_err = holt_winters_forecast(series, horizon)
            rg_fc, rg_err, coefs = ridge_forecast(series, horizon)
            # Pick the lower-holdout-error model per series, and say so.
            best = "ridge" if rg_err <= hw_err else "holt_winters"
            chosen = np.maximum(rg_fc if best == "ridge" else hw_fc, 0.0)
            rows.append({
                "style": style, "region": region,
                "forecast_week1": round(float(chosen[0]), 1),
                "forecast_total_4w": round(float(chosen.sum()), 1),
                "best_model": best,
                "holt_winters_smape": round(hw_err, 4),
                "ridge_smape": round(rg_err, 4),
                "ridge_top_feature": max(coefs, key=lambda k: abs(coefs[k])),
            })
    return pd.DataFrame(rows)
