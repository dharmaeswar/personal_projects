"""Statistics for slide-level comparisons (standard library only).

Wilson score intervals for proportions, Welch's t-test for the
treated-vs-control mean difference, and Cohen's d — implemented from
scratch so the module has no SciPy dependency.
"""

import math


def mean(values):
    return sum(values) / len(values) if values else 0.0


def stddev(values):
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def wilson_interval(successes, trials, z=1.96):
    """Wilson 95% interval for a proportion (successes / trials)."""
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (round(max(0.0, (centre - half) / denom), 4),
            round(min(1.0, (centre + half) / denom), 4))


def _t_cdf_approx(t, df):
    """Approximate two-sided p-value for Student's t (df >= 1).

    Uses the normal approximation with a df correction; accurate
    enough for the demo's screening decisions and clearly labelled.
    """
    x = abs(t)
    # Abramowitz-Stegun normal CDF approximation.
    a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    k = 1.0 / (1.0 + 0.2316419 * x)
    poly = k * (a1 + k * (a2 + k * (a3 + k * (a4 + k * a5))))
    normal_p = 1.0 - math.exp(-x * x / 2.0) / math.sqrt(2 * math.pi) * poly
    # Heavier tails for small df: inflate the tail probability.
    adj = 1.0 + (4.0 / max(df, 1))
    tail = (1.0 - normal_p) * adj
    return round(min(1.0, 2.0 * tail), 4)


def welch_t_test(group_a, group_b):
    """Welch's t-test for two independent samples.

    Returns dict with means, t statistic, df, two-sided p-value and
    Cohen's d. Raises ValueError on empty groups.
    """
    if not group_a or not group_b:
        raise ValueError("both groups need at least one value")
    ma, mb = mean(group_a), mean(group_b)
    sa, sb = stddev(group_a), stddev(group_b)
    na, nb = len(group_a), len(group_b)
    se2 = sa * sa / na + sb * sb / nb
    if se2 == 0:
        return {"mean_a": round(ma, 3), "mean_b": round(mb, 3),
                "t": 0.0, "df": 1.0, "p_value": 1.0, "cohens_d": 0.0}
    t = (ma - mb) / math.sqrt(se2)
    num = se2 * se2
    den = (sa * sa / na) ** 2 / (na - 1) + (sb * sb / nb) ** 2 / (nb - 1)
    df = num / den if den else 1.0
    pooled = math.sqrt(((na - 1) * sa * sa + (nb - 1) * sb * sb)
                       / max(na + nb - 2, 1))
    d = (ma - mb) / pooled if pooled else 0.0
    return {"mean_a": round(ma, 3), "mean_b": round(mb, 3),
            "t": round(t, 3), "df": round(df, 1),
            "p_value": _t_cdf_approx(t, df), "cohens_d": round(d, 3)}
