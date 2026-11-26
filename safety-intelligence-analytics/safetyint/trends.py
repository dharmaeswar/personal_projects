"""Monthly safety rates, rolling trends and emerging-risk flags."""

from __future__ import annotations

import statistics

from .data import CATEGORIES, MonthFlights

RATE_PER = 10000  # rates are expressed per 10,000 flights


def monthly_rates(
    counts: dict[str, dict[str, int]], exposure: list[MonthFlights]
) -> dict[str, dict[str, float]]:
    """Events per 10,000 flights, per month per category."""
    flights = {m.month: m.flights for m in exposure}
    return {
        month: {
            category: counts[month][category] / flights[month] * RATE_PER
            for category in CATEGORIES
        }
        for month in counts
    }


def rolling_rate(series: list[float], window: int = 3) -> list[float]:
    """Trailing rolling mean; positions before the window are None-free
    partial means so the series keeps its length."""
    out: list[float] = []
    for i in range(len(series)):
        start = max(0, i - window + 1)
        out.append(sum(series[start : i + 1]) / (i + 1 - start))
    return out


def trend_slope(series: list[float]) -> float:
    """Least-squares slope per month of a series (0.0 for short series)."""
    n = len(series)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series)) / denom


def baseline_zscores(
    rates: dict[str, dict[str, float]],
    baseline_months: int = 12,
) -> dict[str, dict[str, float]]:
    """Z-score of each month's rate against the first ``baseline_months``
    months of that category (mean and stdev of the baseline window)."""
    months = sorted(rates)
    result: dict[str, dict[str, float]] = {}
    for category in CATEGORIES:
        baseline = [rates[m][category] for m in months[:baseline_months]]
        mean = statistics.mean(baseline)
        stdev = statistics.pstdev(baseline) or 1e-9
        result[category] = {
            m: (rates[m][category] - mean) / stdev for m in months
        }
    return result


def emerging_risks(
    rates: dict[str, dict[str, float]],
    z_threshold: float = 2.0,
    recent_months: int = 3,
) -> list[dict[str, object]]:
    """Categories whose recent rates sit well above their baseline and
    are still rising. Each hit names the evidence, not just a score."""
    months = sorted(rates)
    zscores = baseline_zscores(rates)
    hits: list[dict[str, object]] = []
    for category in CATEGORIES:
        recent = months[-recent_months:]
        recent_z = [zscores[category][m] for m in recent]
        series = [rates[m][category] for m in months]
        # Slope over the last 12 months so a step-up that then plateaus
        # still reads as rising (a 6-month window would miss it).
        slope = trend_slope(series[-12:])
        if max(recent_z) >= z_threshold and slope > 0:
            hits.append(
                {
                    "category": category,
                    "max_recent_z": round(max(recent_z), 2),
                    "recent_rate": round(series[-1], 2),
                    "baseline_rate": round(
                        sum(series[:12]) / 12, 2
                    ),
                    "slope_per_month": round(slope, 3),
                }
            )
    hits.sort(key=lambda h: h["max_recent_z"], reverse=True)  # type: ignore[arg-type]
    return hits
