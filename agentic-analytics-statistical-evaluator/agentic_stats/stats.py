"""Core statistics for the agentic analytics evaluator.

Pure standard library. Implements Welch's two-sample t-test, the chi-square
test of independence, bootstrap confidence intervals, Cohen's d, Bonferroni
correction and a normal-approximation power check. The t and chi-square
p-values use the regularised incomplete beta / gamma functions (Numerical
Recipes continued-fraction forms), so no SciPy is needed.
"""

import math
import random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def variance(xs, ddof=1):
    xs = list(xs)
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - ddof)


def std(xs, ddof=1):
    return math.sqrt(variance(xs, ddof))


# --- regularised incomplete beta, via continued fractions -------------------

def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 501):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def betainc_reg(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    """CDF of Student's t with df degrees of freedom."""
    x = df / (df + t * t)
    ib = betainc_reg(df / 2.0, 0.5, x)
    if t >= 0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


def welch_t_test(a, b):
    """Welch's two-sample t-test. Returns dict with t, df and two-sided p."""
    a, b = list(a), list(b)
    ma, mb = mean(a), mean(b)
    va, vb = variance(a), variance(b)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    t = (ma - mb) / se
    num = (va / na + vb / nb) ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df = num / den
    p = 2.0 * (1.0 - t_cdf(abs(t), df))
    return {"t": t, "df": df, "p": p, "mean_diff": ma - mb}


# --- regularised incomplete gamma / chi-square ------------------------------

def _gser(a, x):
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(500):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - gln)


def _gcf(a, x):
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / 1e-300
    d = 1.0 / b
    h = d
    for i in range(1, 501):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def gammainc_reg(a, x):
    """Regularised lower incomplete gamma P(a, x)."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)


def chi_square_test(table):
    """Chi-square test of independence for a 2-D contingency table.

    Returns dict with chi2, df and p. Uses Yates-free Pearson statistic.
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
    df = (rows - 1) * (cols - 1)
    p = 1.0 - gammainc_reg(df / 2.0, chi2 / 2.0)
    return {"chi2": chi2, "df": df, "p": p}


# --- effect size, bootstrap CI, corrections, power --------------------------

def cohens_d(a, b):
    a, b = list(a), list(b)
    pooled = math.sqrt(((len(a) - 1) * variance(a)
                        + (len(b) - 1) * variance(b))
                       / (len(a) + len(b) - 2))
    return (mean(a) - mean(b)) / pooled


def bootstrap_ci_mean_diff(a, b, reps=2000, seed=42, level=0.95):
    """Percentile bootstrap CI for the difference of means (deterministic)."""
    rng = random.Random(seed)
    a, b = list(a), list(b)
    diffs = []
    for _ in range(reps):
        sa = [rng.choice(a) for _ in a]
        sb = [rng.choice(b) for _ in b]
        diffs.append(mean(sa) - mean(sb))
    diffs.sort()
    alpha = 1.0 - level
    lo = diffs[int(alpha / 2 * reps)]
    hi = diffs[int((1.0 - alpha / 2) * reps) - 1]
    return (lo, hi)


def bonferroni(p_values, alpha=0.05):
    """Bonferroni-adjusted significance decisions for a list of p-values."""
    m = len(p_values)
    return [p * m < alpha for p in p_values]


def interaction_t_test(a_high, b_high, a_low, b_low):
    """Test whether the treatment effect differs between two subgroups.

    Compares (mean(a_high) - mean(b_high)) against (mean(a_low) - mean(b_low))
    with a Welch-style t-test on the difference of differences. Returns a dict
    with t, df and two-sided p.
    """
    groups = [list(g) for g in (a_high, b_high, a_low, b_low)]
    means = [mean(g) for g in groups]
    vars_ = [variance(g) for g in groups]
    ns = [len(g) for g in groups]
    diff = (means[0] - means[1]) - (means[2] - means[3])
    se2_terms = [v / n for v, n in zip(vars_, ns)]
    se = math.sqrt(sum(se2_terms))
    t = diff / se
    num = sum(se2_terms) ** 2
    den = sum((v / n) ** 2 / (n - 1) for v, n in zip(vars_, ns))
    df = num / den
    p = 2.0 * (1.0 - t_cdf(abs(t), df))
    return {"t": t, "df": df, "p": p, "interaction": diff}


def power_two_sample(d, n_per_arm, alpha=0.05):
    """Normal-approximation power for a two-sample test of effect size d."""
    z_alpha = 1.959964  # two-sided 0.05
    z_beta = d * math.sqrt(n_per_arm / 2.0) - z_alpha
    # Normal CDF via erf.
    return 0.5 * (1.0 + math.erf(z_beta / math.sqrt(2.0)))
