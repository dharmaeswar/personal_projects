"""Error metrics for comparing a solver's predictions with reference values."""

from __future__ import annotations

import math


def _check(predicted: list[float], reference: list[float]) -> None:
    if not predicted or not reference:
        raise ValueError("inputs must be non-empty")
    if len(predicted) != len(reference):
        raise ValueError("predicted and reference must have the same length")


def mae(predicted: list[float], reference: list[float]) -> float:
    _check(predicted, reference)
    return sum(abs(p - r) for p, r in zip(predicted, reference)) / len(predicted)


def rmse(predicted: list[float], reference: list[float]) -> float:
    _check(predicted, reference)
    return math.sqrt(sum((p - r) ** 2 for p, r in zip(predicted, reference)) / len(predicted))


def max_abs_error(predicted: list[float], reference: list[float]) -> float:
    _check(predicted, reference)
    return max(abs(p - r) for p, r in zip(predicted, reference))


def within_tolerance(predicted: list[float], reference: list[float], tolerance: float) -> float:
    """Fraction of predictions within `tolerance` (absolute) of the reference."""
    _check(predicted, reference)
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    hits = sum(1 for p, r in zip(predicted, reference) if abs(p - r) <= tolerance)
    return hits / len(predicted)
