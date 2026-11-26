"""Ridge-regression production forecaster (numpy only, no sklearn).

Target: next-month oil rate (bbl) for a well, from the feature set built in
features.py. Ridge regression with a closed-form solution; features are
standardised on the training split only. Splits are by time (earlier months
train, later months test) — never a random split, so the backtest mirrors
how the model would actually be used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS


def _design(df: pd.DataFrame) -> np.ndarray:
    return df[FEATURE_COLUMNS].to_numpy(dtype=float)


def train_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> dict:
    """Closed-form ridge: w = (X'X + alpha I)^-1 X'y (no penalty on bias)."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std > 0, std, 1.0)
    Xs = (X - mean) / std
    Xb = np.column_stack([Xs, np.ones(len(Xs))])
    p = Xb.shape[1]
    reg = np.eye(p) * alpha
    reg[-1, -1] = 0.0  # do not penalise the intercept
    w = np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)
    return {"weights": w, "mean": mean, "std": std, "alpha": alpha,
            "n_features": len(FEATURE_COLUMNS)}


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    """Predict next-month oil (bbl); negative predictions are clipped to 0."""
    Xs = (X - model["mean"]) / model["std"]
    Xb = np.column_stack([Xs, np.ones(len(Xs))])
    return np.clip(Xb @ model["weights"], 0.0, None)


def backtest(df: pd.DataFrame, train_months: int = 24,
             alpha: float = 1.0) -> dict:
    """Train on months < train_months, test on later months, per well.

    The target for month m is the oil rate of month m+1, so the last month
    of each well has no target and is dropped.
    """
    work = df.sort_values(["api_number", "month_index"]).copy()
    work["target_next_oil"] = work.groupby("api_number")["oil_bbl"].shift(-1)
    work = work.dropna(subset=["target_next_oil"])
    train = work[work["month_index"] < train_months]
    test = work[work["month_index"] >= train_months]
    model = train_ridge(_design(train), train["target_next_oil"].to_numpy(), alpha)
    pred = predict(model, _design(test))
    actual = test["target_next_oil"].to_numpy(dtype=float)
    rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
    mape = float(np.mean(np.abs(pred - actual) / np.maximum(actual, 1.0)))
    baseline = float(np.sqrt(np.mean((test["oil_bbl_lag1"].to_numpy() - actual) ** 2)))
    return {
        "model": model,
        "rmse_bbl": rmse,
        "mape": mape,
        "baseline_persistence_rmse_bbl": baseline,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "beats_baseline": rmse < baseline,
    }
