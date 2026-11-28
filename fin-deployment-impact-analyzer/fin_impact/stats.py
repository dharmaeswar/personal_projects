"""Statistics for before/after deployment comparisons (stdlib only).

Wilson intervals for rates, Welch's t-test for handle-time means,
and uplift with a confidence interval — the numbers that decide
whether a deployment really moved the metric or just moved by luck.
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
    """Wilson 95% interval for a rate (successes / trials)."""
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (round(max(0.0, (centre - half) / denom), 4),
            round(min(1.0, (centre + half) / denom), 4))


def welch_t_test(group_a, group_b):
    """Welch's t-test; returns means, t, df, and an approximate p-value."""
    if not group_a or not group_b:
        raise ValueError("both groups need at least one value")
    ma, mb = mean(group_a), mean(group_b)
    sa, sb = stddev(group_a), stddev(group_b)
    na, nb = len(group_a), len(group_b)
    se2 = sa * sa / na + sb * sb / nb
    if se2 == 0:
        return {"mean_a": round(ma, 3), "mean_b": round(mb, 3),
                "t": 0.0, "df": 1.0, "p_value": 1.0}
    t = (ma - mb) / math.sqrt(se2)
    num = se2 * se2
    den = (sa * sa / na) ** 2 / (na - 1) + (sb * sb / nb) ** 2 / (nb - 1)
    df = num / den if den else 1.0
    p = _two_sided_p(t, df)
    return {"mean_a": round(ma, 3), "mean_b": round(mb, 3),
            "t": round(t, 3), "df": round(df, 1), "p_value": p}


def _two_sided_p(t, df):
    """Approximate two-sided p-value (normal approx, df-adjusted tail)."""
    x = abs(t)
    a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    k = 1.0 / (1.0 + 0.2316419 * x)
    poly = k * (a1 + k * (a2 + k * (a3 + k * (a4 + k * a5))))
    normal_p = 1.0 - math.exp(-x * x / 2.0) / math.sqrt(2 * math.pi) * poly
    tail = (1.0 - normal_p) * (1.0 + 4.0 / max(df, 1))
    return round(min(1.0, 2.0 * tail), 4)


def uplift(before_rate, after_rate, n_before, n_after):
    """Absolute uplift with a 95% interval (two-proportion z-interval)."""
    diff = after_rate - before_rate
    se = math.sqrt(before_rate * (1 - before_rate) / max(n_before, 1)
                   + after_rate * (1 - after_rate) / max(n_after, 1))
    return {"uplift": round(diff, 4),
            "ci_low": round(diff - 1.96 * se, 4),
            "ci_high": round(diff + 1.96 * se, 4)}
