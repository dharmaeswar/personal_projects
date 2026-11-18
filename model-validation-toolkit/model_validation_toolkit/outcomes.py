"""Outcomes analysis: compare model predictions against realised values."""
import math
from typing import Dict, Sequence


def backtest_summary(predicted: Sequence[float], realised: Sequence[float]) -> Dict[str, float]:
    """Return bias, MAE, RMSE and hit-rate within a 5% tolerance band."""
    if len(predicted) != len(realised) or not predicted:
        raise ValueError("predicted and realised must be non-empty and equal length")
    errors = [p - r for p, r in zip(predicted, realised)]
    n = len(errors)
    bias = sum(errors) / n
    mae = sum(abs(e) for e in errors) / n
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    hits = sum(1 for p, r in zip(predicted, realised) if r == 0 or abs(p - r) / abs(r) <= 0.05)
    return {"n": float(n), "bias": bias, "mae": mae, "rmse": rmse, "hit_rate_5pct": hits / n}
