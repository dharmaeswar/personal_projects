"""Drift checks for model inputs and scores."""
import math
from typing import Sequence


def mean_drift_bps(baseline: Sequence[float], current: Sequence[float]) -> float:
    """Mean shift between two samples, expressed in basis points of the baseline mean."""
    if not baseline or not current:
        raise ValueError("samples must be non-empty")
    base_mean = sum(baseline) / len(baseline)
    if base_mean == 0:
        raise ValueError("baseline mean is zero")
    cur_mean = sum(current) / len(current)
    return (cur_mean - base_mean) / abs(base_mean) * 10_000


def population_stability_index(expected_pct: Sequence[float], actual_pct: Sequence[float]) -> float:
    """PSI over matching buckets; values above 0.25 usually signal material drift."""
    if len(expected_pct) != len(actual_pct) or not expected_pct:
        raise ValueError("bucket lists must be non-empty and equal length")
    psi = 0.0
    for e, a in zip(expected_pct, actual_pct):
        e = max(e, 1e-6)
        a = max(a, 1e-6)
        psi += (a - e) * math.log(a / e)
    return psi
