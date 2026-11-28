"""Experiment design: power, sample size, minimum detectable effect, SRM checks.

Formulas are the standard two-sample normal approximations used by
experimentation platforms before an experiment is launched.
"""

import math

from scipy import stats


def _z(power):
    return stats.norm.ppf(power)


def sample_size_proportion(baseline_rate, mde, alpha=0.05, power=0.80,
                           allocation=0.5):
    """Per-variant sample size for a two-proportion A/B test.

    baseline_rate: control conversion rate; mde: absolute lift to detect.
    allocation: share of traffic in control (0.5 = 50/50 split).
    Returns the per-variant n (rounded up); the caller multiplies by 2
    for the total, or by 1/allocation and 1/(1-allocation) for uneven splits.
    """
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be in (0, 1)")
    if mde <= 0:
        raise ValueError("mde must be positive")
    p1 = baseline_rate
    p2 = baseline_rate + mde
    if not 0 < p2 < 1:
        raise ValueError("baseline_rate + mde must be in (0, 1)")
    z_alpha = _z(1 - alpha / 2)
    z_beta = _z(power)
    p_bar = (p1 + p2) / 2
    var_null = 2 * p_bar * (1 - p_bar)
    var_alt = p1 * (1 - p1) + p2 * (1 - p2)
    n = ((z_alpha * math.sqrt(var_null) + z_beta * math.sqrt(var_alt)) ** 2
         / mde ** 2)
    return math.ceil(n)


def sample_size_continuous(std, mde, alpha=0.05, power=0.80):
    """Per-variant sample size for a two-sample test on a continuous metric."""
    if std <= 0 or mde <= 0:
        raise ValueError("std and mde must be positive")
    z_alpha = _z(1 - alpha / 2)
    z_beta = _z(power)
    n = 2 * std ** 2 * (z_alpha + z_beta) ** 2 / mde ** 2
    return math.ceil(n)


def minimum_detectable_effect(baseline_rate, n_per_variant, alpha=0.05,
                              power=0.80):
    """Smallest absolute lift detectable with n users per variant (proportions)."""
    if n_per_variant <= 0:
        raise ValueError("n_per_variant must be positive")
    z_alpha = _z(1 - alpha / 2)
    z_beta = _z(power)
    # Binary search on the mde: n(mde) is monotone decreasing in mde.
    lo, hi = 1e-9, min(0.5, 1 - baseline_rate - 1e-9)
    for _ in range(100):
        mid = (lo + hi) / 2
        if sample_size_proportion(baseline_rate, mid, alpha, power) <= n_per_variant:
            hi = mid
        else:
            lo = mid
    return hi


def check_srm(n_control, n_treatment, expected_control_share=0.5):
    """Sample-ratio-mismatch check: chi-square test on the observed split.

    Returns a dict with the chi-square statistic, p-value and a boolean
    flag (True = mismatch detected at alpha 0.01, the usual platform bar).
    """
    total = n_control + n_treatment
    if total <= 0:
        raise ValueError("need at least one observation")
    expected_c = total * expected_control_share
    expected_t = total * (1 - expected_control_share)
    chi2 = ((n_control - expected_c) ** 2 / expected_c
            + (n_treatment - expected_t) ** 2 / expected_t)
    p_value = float(1 - stats.chi2.cdf(chi2, df=1))
    return {"chi2": float(chi2), "p_value": p_value, "srm_detected": p_value < 0.01}
