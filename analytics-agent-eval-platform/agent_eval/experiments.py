"""AI-powered experiment analysis: interpret A/B results, flag issues,
recommend ship / no-ship.

Perplexity's Data Acceleration work includes agents that interpret A/B
test results, flag statistical issues, identify likely drivers and draft
ship/no-ship recommendations. This module is the statistical core such an
agent would call: a two-proportion z-test for a binary primary metric,
a sample-ratio-mismatch (SRM) check on the allocation, optional
guardrail checks, and a recommendation that is explicit about why.

It never peeks at raw user data: it takes aggregate counts only. The
normal approximation is used for the z-test and the SRM chi-square
p-value; both are documented limits, and the module refuses to call a
result significant when the sample is too small to support the test.
All data is synthetic and seeded; nothing here is real experiment data.
"""

from __future__ import annotations

import math

MIN_SAMPLE_PER_ARM = 30


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - _norm_cdf(abs(z)))


def analyze_experiment(control_n: int, control_conversions: int,
                       treatment_n: int, treatment_conversions: int,
                       *, alpha: float = 0.05,
                       guardrails: list[dict] | None = None,
                       segments: list[dict] | None = None) -> dict:
    """Analyse one A/B test and recommend SHIP, NO-SHIP or HOLD.

    ``guardrails``: optional list of ``{"name", "control_rate",
    "treatment_rate", "max_relative_drop"}``; a guardrail fails when the
    treatment rate falls more than ``max_relative_drop`` below control.
    ``segments``: optional list of ``{"name", "control_rate",
    "treatment_rate"}`` used to flag segments moving against the overall
    result. Returns rates, uplift, z, p-value, a 95% confidence interval
    on the absolute difference, the SRM check and the recommendation
    with its reasons.
    """
    if min(control_n, treatment_n) < MIN_SAMPLE_PER_ARM:
        return {
            "recommendation": "HOLD",
            "reasons": [f"sample too small: smallest arm is"
                        f" {min(control_n, treatment_n)} users;"
                        f" need at least {MIN_SAMPLE_PER_ARM} per arm"
                        " before calling a result"],
            "significant": False,
            "p_value": None,
            "control_rate": control_conversions / control_n if control_n else 0.0,
            "treatment_rate": (treatment_conversions / treatment_n
                               if treatment_n else 0.0),
        }
    p_c = control_conversions / control_n
    p_t = treatment_conversions / treatment_n
    diff = p_t - p_c
    pooled = (control_conversions + treatment_conversions) / (control_n + treatment_n)
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / control_n + 1.0 / treatment_n))
    z = diff / se if se > 0 else 0.0
    p_value = _two_sided_p(z)
    half_width = 1.96 * se
    ci = (diff - half_width, diff + half_width)

    # Sample ratio mismatch: allocation should be 50/50; a chi-square
    # statistic on 1 degree of freedom, p from the normal approximation.
    total = control_n + treatment_n
    expected = total / 2.0
    chi2 = ((control_n - expected) ** 2 + (treatment_n - expected) ** 2) / expected
    srm_p = 1.0 - math.erf(math.sqrt(chi2 / 2.0)) if chi2 > 0 else 1.0
    srm = {"chi2": round(chi2, 3), "p_value": round(srm_p, 4),
           "flagged": srm_p < 0.01}

    failed_guardrails = []
    for g in guardrails or []:
        base = g["control_rate"]
        drop = (base - g["treatment_rate"]) / base if base else 0.0
        if drop > g["max_relative_drop"]:
            failed_guardrails.append(
                {"name": g["name"], "relative_drop": round(drop, 4)})

    opposing_segments = []
    for s in segments or []:
        if (diff > 0 and s["treatment_rate"] < s["control_rate"]) or \
           (diff < 0 and s["treatment_rate"] > s["control_rate"]):
            opposing_segments.append(s["name"])

    significant = p_value < alpha
    reasons: list[str] = []
    if srm["flagged"]:
        reasons.append(f"sample ratio mismatch (chi2={chi2:.1f},"
                       f" p={srm_p:.4f}): allocation is not 50/50, so the"
                       " result cannot be trusted until the assignment bug"
                       " is found")
    if failed_guardrails:
        reasons.append("guardrail(s) breached: " + ", ".join(
            f"{g['name']} fell {g['relative_drop']:.1%}" for g in failed_guardrails))
    if opposing_segments:
        reasons.append("segment(s) move against the overall result: " +
                       ", ".join(opposing_segments) +
                       " — check for a Simpson's-paradox split before shipping")
    if not significant:
        reasons.append(f"not significant at alpha={alpha} (p={p_value:.4f});"
                       " the observed difference could be noise")
    if significant and diff > 0:
        reasons.append(f"treatment lifts the metric by {diff:.2%} relative"
                       f" {diff / p_c:.1%} (95% CI {ci[0]:.2%} to {ci[1]:.2%})")
    if significant and diff < 0:
        reasons.append(f"treatment hurts the metric by {diff:.2%} (95% CI"
                       f" {ci[0]:.2%} to {ci[1]:.2%})")

    if srm["flagged"] or failed_guardrails or opposing_segments:
        recommendation = "HOLD"
    elif not significant:
        recommendation = "HOLD"
    elif diff > 0:
        recommendation = "SHIP"
    else:
        recommendation = "NO-SHIP"

    return {
        "recommendation": recommendation,
        "reasons": reasons,
        "significant": significant,
        "p_value": round(p_value, 4),
        "z": round(z, 3),
        "control_rate": round(p_c, 4),
        "treatment_rate": round(p_t, 4),
        "absolute_diff": round(diff, 4),
        "relative_uplift": round(diff / p_c, 4) if p_c else None,
        "ci_95": (round(ci[0], 4), round(ci[1], 4)),
        "srm": srm,
        "failed_guardrails": failed_guardrails,
        "opposing_segments": opposing_segments,
    }
