"""Comparison tools: is a change real, or noise, bad data, or bad infra?

Two results are compared with their sample sizes and uncertainty exposed:
for rates, a Wilson score interval; for means, a normal-approximation
interval from the sample standard deviation. A change counts as a
regression only when the intervals do not overlap in the bad direction —
a point-estimate move inside the noise is reported as inconclusive, not
as a regression. A separate classifier helps users tell a model
regression apart from a data, simulator, or infrastructure failure, using
the signals that accompany the numbers (coverage drop, missing inputs,
failed jobs) rather than the metric value alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z_95 = 1.96


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def mean_interval(values: list[float], z: float = Z_95) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return (mean, mean)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    margin = z * math.sqrt(var / len(values))
    return (mean - margin, mean + margin)


@dataclass
class Comparison:
    metric_name: str
    baseline_value: float | None
    candidate_value: float | None
    baseline_n: int
    candidate_n: int
    baseline_coverage: float
    candidate_coverage: float
    delta: float | None
    verdict: str  # "regression" | "improvement" | "no_change" | "inconclusive" | "not_comparable"
    reason: str


def compare_rates(baseline_successes: int, baseline_n: int,
                  candidate_successes: int, candidate_n: int,
                  metric_name: str, higher_is_better: bool,
                  baseline_coverage: float = 1.0, candidate_coverage: float = 1.0,
                  min_n: int = 30) -> Comparison:
    if baseline_n < min_n or candidate_n < min_n:
        return Comparison(metric_name, None, None, baseline_n, candidate_n,
                          baseline_coverage, candidate_coverage, None,
                          "not_comparable",
                          f"sample size below minimum ({min_n}): "
                          f"baseline n={baseline_n}, candidate n={candidate_n}")
    b_lo, b_hi = wilson_interval(baseline_successes, baseline_n)
    c_lo, c_hi = wilson_interval(candidate_successes, candidate_n)
    b_val = baseline_successes / baseline_n
    c_val = candidate_successes / candidate_n
    delta = c_val - b_val
    if higher_is_better:
        if c_hi < b_lo:
            verdict, reason = "regression", "candidate interval entirely below baseline interval"
        elif c_lo > b_hi:
            verdict, reason = "improvement", "candidate interval entirely above baseline interval"
        elif abs(delta) < 1e-9:
            verdict, reason = "no_change", "values equal"
        else:
            verdict, reason = "inconclusive", "intervals overlap; change is within noise"
    else:
        if c_lo > b_hi:
            verdict, reason = "regression", "candidate interval entirely above baseline interval"
        elif c_hi < b_lo:
            verdict, reason = "improvement", "candidate interval entirely below baseline interval"
        elif abs(delta) < 1e-9:
            verdict, reason = "no_change", "values equal"
        else:
            verdict, reason = "inconclusive", "intervals overlap; change is within noise"
    return Comparison(metric_name, b_val, c_val, baseline_n, candidate_n,
                      baseline_coverage, candidate_coverage, round(delta, 4), verdict, reason)


def classify_failure(*, coverage: float, missing_inputs: int, failed_jobs: int,
                     total_jobs: int, metric_changed: bool) -> str:
    """Distinguish a model regression from data/sim/infra failure.

    A metric move with healthy coverage and no failed jobs looks like the
    model. A coverage drop or missing inputs points at data. Failed jobs
    point at infrastructure. Returns a plain-word cause label.
    """
    if failed_jobs > 0 and total_jobs > 0 and failed_jobs / total_jobs >= 0.1:
        return "infrastructure: job failures dominate — check compute/storage before blaming the model"
    if coverage < 0.8 or missing_inputs > 0:
        return "data: coverage dropped or inputs missing — the measurement is incomplete, not a model regression"
    if metric_changed:
        return "model: coverage and infra healthy — the change most likely comes from the model"
    return "no_failure: metric and pipeline both look healthy"
