"""Metrics with statistical rigor.

Eval scores are noisy: a 24-case suite that moves from 75% to 83% may have
moved by luck. So every reported rate carries a bootstrap 95% confidence
interval, and every before/after comparison is a paired test on the same
cases (McNemar's exact test via the binomial distribution), not a bare
difference of two percentages.
"""

import math
import random


def pass_rate(results):
    """Share of results that passed; None when there are no results."""
    if not results:
        return None
    return sum(1 for r in results if r["passed"]) / len(results)


def bootstrap_ci(values, n_boot=2000, seed=42, level=0.95):
    """Percentile bootstrap CI for the mean of 0/1 (or numeric) values.

    Returns (low, high). Deterministic for a fixed seed. With tiny suites
    the interval is wide -- that is the point: it says how much the number
    can be trusted.
    """
    if not values:
        return (None, None)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1 - level) / 2
    lo = means[int(alpha * n_boot)]
    hi = means[min(int((1 - alpha) * n_boot), n_boot - 1)]
    return (round(lo, 3), round(hi, 3))


def _binom_pmf(n, k, p=0.5):
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def mcnemar_exact(before, after):
    """Exact McNemar test on paired pass/fail verdicts.

    ``before``/``after`` are equal-length lists of booleans for the same
    cases in the same order. Only the discordant pairs (pass->fail and
    fail->pass) carry information. Returns a two-sided exact p-value from
    the binomial distribution; 1.0 when there are no discordant pairs.
    """
    if len(before) != len(after):
        raise ValueError("paired lists must be the same length")
    b = sum(1 for x, y in zip(before, after) if x and not y)   # got worse
    c = sum(1 for x, y in zip(before, after) if not x and y)   # got better
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(_binom_pmf(n, i) for i in range(0, k + 1)) * 2
    return round(min(p, 1.0), 4)


def paired_comparison(before, after):
    """Full paired comparison: rates, delta, McNemar p-value, verdict.

    Verdict is IMPROVEMENT / REGRESSION / NO CHANGE at alpha = 0.05,
    based on the paired test -- not on the raw delta alone.
    """
    rate_before = pass_rate(before)
    rate_after = pass_rate(after)
    p = mcnemar_exact([r["passed"] for r in before],
                      [r["passed"] for r in after])
    delta = round(rate_after - rate_before, 3)
    if p < 0.05 and delta > 0:
        verdict = "IMPROVEMENT"
    elif p < 0.05 and delta < 0:
        verdict = "REGRESSION"
    else:
        verdict = "NO CHANGE"
    return {"rate_before": round(rate_before, 3),
            "rate_after": round(rate_after, 3),
            "delta": delta, "mcnemar_p": p, "verdict": verdict,
            "n": len(before)}


def summarize(results, n_boot=2000, seed=42):
    """Per-surface and overall summary with bootstrap CIs."""
    by_surface = {}
    for r in results:
        by_surface.setdefault(r["surface"], []).append(r)
    surfaces = {}
    for surface, rs in sorted(by_surface.items()):
        rate = pass_rate(rs)
        lo, hi = bootstrap_ci([1 if r["passed"] else 0 for r in rs],
                              n_boot=n_boot, seed=seed)
        surfaces[surface] = {"n": len(rs), "pass_rate": round(rate, 3),
                             "ci_95": [lo, hi],
                             "failed": [r["case_id"] for r in rs
                                        if not r["passed"]]}
    rate = pass_rate(results)
    lo, hi = bootstrap_ci([1 if r["passed"] else 0 for r in results],
                          n_boot=n_boot, seed=seed)
    return {"n": len(results), "pass_rate": round(rate, 3),
            "ci_95": [lo, hi], "surfaces": surfaces}
