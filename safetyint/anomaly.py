"""Outlier detection on monthly safety rates (IQR rule + z-score)."""

from __future__ import annotations

import statistics

from .data import CATEGORIES


def _quartiles(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    lower = ordered[: n // 2]
    upper = ordered[(n + 1) // 2 :]
    return statistics.median(lower), statistics.median(upper)


def find_anomalies(
    rates: dict[str, dict[str, float]],
    iqr_multiplier: float = 1.5,
) -> list[dict[str, object]]:
    """Months whose rate is an IQR outlier for its category.

    Returns one row per anomalous month, with the fence it crossed, so
    a reviewer can check the flag without re-running the math.
    """
    months = sorted(rates)
    hits: list[dict[str, object]] = []
    for category in CATEGORIES:
        series = [rates[m][category] for m in months]
        if len(series) < 4:
            continue
        q1, q3 = _quartiles(series)
        iqr = q3 - q1
        upper_fence = q3 + iqr_multiplier * iqr
        mean = statistics.mean(series)
        stdev = statistics.pstdev(series) or 1e-9
        for month, value in zip(months, series):
            if value > upper_fence:
                hits.append(
                    {
                        "month": month,
                        "category": category,
                        "rate": round(value, 2),
                        "upper_fence": round(upper_fence, 2),
                        "z": round((value - mean) / stdev, 2),
                    }
                )
    hits.sort(key=lambda h: (h["month"], h["category"]))  # type: ignore[arg-type]
    return hits
