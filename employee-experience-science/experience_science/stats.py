"""Statistical helpers implemented from scratch (standard library only).

Welch's two-sample t-test with a normal approximation for the p-value
(valid for the large groups used here), chi-square test with an exact
p-value via the regularised incomplete gamma function, bootstrap
confidence intervals, Cohen's d and Pearson correlation.
"""

import math
import random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def variance(xs):
    xs = list(xs)
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def std(xs):
    return math.sqrt(variance(xs))


def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def welch_t(a, b):
    """Return (t_statistic, two_sided_p_value, cohens_d) for two samples."""
    a, b = list(a), list(b)
    ma, mb = mean(a), mean(b)
    va, vb = variance(a), variance(b)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    t = (ma - mb) / se if se > 0 else 0.0
    # Normal approximation to the t distribution (groups here are large).
    p = 2.0 * (1.0 - _norm_cdf(abs(t)))
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    d = (ma - mb) / pooled if pooled > 0 else 0.0
    return t, p, d


def _gammainc_reg(a, x):
    """Regularised lower incomplete gamma P(a, x) (Numerical Recipes)."""
    if x < 0 or a <= 0:
        raise ValueError("invalid arguments")
    if x == 0:
        return 0.0
    if x < a + 1.0:
        # Series representation.
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(1000):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-12:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Continued fraction representation for Q(a, x); P = 1 - Q.
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def chi_square_test(table):
    """Pearson chi-square test on a 2-D contingency table.

    Returns (chi2_statistic, degrees_of_freedom, p_value).
    """
    rows = len(table)
    cols = len(table[0])
    row_tot = [sum(r) for r in table]
    col_tot = [sum(table[r][c] for r in range(rows)) for c in range(cols)]
    total = sum(row_tot)
    chi2 = 0.0
    for r in range(rows):
        for c in range(cols):
            expected = row_tot[r] * col_tot[c] / total
            chi2 += (table[r][c] - expected) ** 2 / expected
    dof = (rows - 1) * (cols - 1)
    p = 1.0 - _gammainc_reg(dof / 2.0, chi2 / 2.0)
    return chi2, dof, p


def bootstrap_ci_mean_diff(a, b, n_boot=2000, seed=7, level=0.95):
    """Bootstrap confidence interval for (mean(a) - mean(b))."""
    rng = random.Random(seed)
    a, b = list(a), list(b)
    diffs = []
    for _ in range(n_boot):
        sa = [rng.choice(a) for _ in a]
        sb = [rng.choice(b) for _ in b]
        diffs.append(mean(sa) - mean(sb))
    diffs.sort()
    alpha = (1.0 - level) / 2.0
    lo = diffs[int(alpha * n_boot)]
    hi = diffs[int((1.0 - alpha) * n_boot) - 1]
    return lo, hi


def pearson(xs, ys):
    xs, ys = list(xs), list(ys)
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den > 0 else 0.0


def bonferroni(p_values, alpha=0.05):
    """Return (corrected_alpha, [significant flags]) for m tests."""
    m = len(p_values)
    corrected = alpha / m
    return corrected, [p < corrected for p in p_values]
