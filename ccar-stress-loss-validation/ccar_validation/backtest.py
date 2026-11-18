"""Outcomes analysis (backtest): bias, MAE, RMSE, hit rate, calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(actual: np.ndarray, predicted: np.ndarray, tolerance: float = 0.01) -> dict:
    """Compute outcomes-analysis metrics for loss-rate forecasts.

    tolerance: absolute loss-rate band for the hit rate (default 1 pp).
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = predicted - actual
    return {
        "bias": float(np.mean(errors)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "hit_rate": float(np.mean(np.abs(errors) <= tolerance)),
        "n": int(len(actual)),
    }


def calibration_by_decile(
    actual: np.ndarray, predicted: np.ndarray, n_deciles: int = 10
) -> pd.DataFrame:
    """Mean actual vs mean predicted loss rate by predicted-decile bucket."""
    df = pd.DataFrame({"actual": actual, "predicted": predicted})
    df["decile"] = pd.qcut(df["predicted"], q=n_deciles, labels=False, duplicates="drop") + 1
    grouped = (
        df.groupby("decile")
        .agg(
            n=("actual", "size"),
            mean_actual=("actual", "mean"),
            mean_predicted=("predicted", "mean"),
        )
        .reset_index()
    )
    grouped["calibration_gap"] = grouped["mean_predicted"] - grouped["mean_actual"]
    return grouped


def backtest_all(actual: np.ndarray, forecasts: dict, tolerance: float = 0.01) -> dict:
    """Run compute_metrics for each model in ``forecasts``."""
    return {name: compute_metrics(actual, pred, tolerance) for name, pred in forecasts.items()}
