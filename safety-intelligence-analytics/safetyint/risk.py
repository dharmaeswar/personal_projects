"""Severity-weighted risk scores and an SMS-style risk matrix."""

from __future__ import annotations

from .data import CATEGORIES, SEVERITY_WEIGHTS
from .trends import trend_slope


def risk_scores(
    rates: dict[str, dict[str, float]],
    recent_months: int = 6,
) -> list[dict[str, object]]:
    """Rank categories by recent severity-weighted rate, adjusted for
    trend direction. Score = severity weight x recent mean rate x
    (1 + slope), floored so a falling trend cannot go negative."""
    months = sorted(rates)
    recent = months[-recent_months:]
    scored: list[dict[str, object]] = []
    for category in CATEGORIES:
        series = [rates[m][category] for m in recent]
        mean_rate = sum(series) / len(series)
        slope = trend_slope([rates[m][category] for m in months[-12:]])
        factor = max(0.5, 1.0 + slope)
        score = SEVERITY_WEIGHTS[category] * mean_rate * factor
        scored.append(
            {
                "category": category,
                "score": round(score, 2),
                "recent_rate": round(mean_rate, 2),
                "severity_weight": SEVERITY_WEIGHTS[category],
                "trend": "rising" if slope > 0.05 else "falling" if slope < -0.05 else "flat",
            }
        )
    scored.sort(key=lambda s: s["score"], reverse=True)  # type: ignore[arg-type]
    return scored


def risk_matrix_cell(likelihood: str, severity: int) -> str:
    """SMS-style cell label from a likelihood band and severity 1-5.

    Likelihood bands: low (rate < 2), medium (2-6), high (> 6) per
    10,000 flights. Severity 4-5 with high likelihood is the top band.
    """
    if severity >= 4 and likelihood == "high":
        return "HIGH — priority review"
    if severity >= 4 and likelihood == "medium":
        return "MEDIUM-HIGH — monitor closely"
    if severity >= 3 and likelihood == "high":
        return "MEDIUM-HIGH — monitor closely"
    if likelihood == "low" and severity <= 2:
        return "LOW — routine monitoring"
    return "MEDIUM — scheduled review"


def likelihood_band(rate: float) -> str:
    """Rate per 10,000 flights mapped to a likelihood band."""
    if rate < 2.0:
        return "low"
    if rate <= 6.0:
        return "medium"
    return "high"
