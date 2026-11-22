"""Risk-model backtesting: VaR exceptions and regulatory tests.

Implements the backtests a model risk team runs on a VaR model:
historical VaR, expected shortfall, exception counting, the Kupiec
proportion-of-failures test and the Christoffersen independence test.
"""

import math

import numpy as np


def historical_var(returns, alpha=0.05):
    """One-day historical VaR at confidence 1 - alpha (positive number)."""
    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        raise ValueError("returns must not be empty")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    return float(-np.quantile(r, alpha))


def expected_shortfall(returns, alpha=0.05):
    """Expected shortfall: mean loss beyond VaR (positive number)."""
    r = np.asarray(returns, dtype=float)
    var = historical_var(r, alpha)
    tail = r[r <= -var]
    if len(tail) == 0:
        return var
    return float(-np.mean(tail))


def count_exceptions(returns, var_series):
    """Days where the loss exceeded the VaR forecast (1 = breach)."""
    r = np.asarray(returns, dtype=float)
    v = np.asarray(var_series, dtype=float)
    if r.shape != v.shape:
        raise ValueError("returns and var_series must align")
    return (r < -v).astype(int)


def kupiec_pof(exceptions, alpha=0.05):
    """Kupiec proportion-of-failures likelihood-ratio statistic.

    Returns (statistic, reject_at_5pct). The 5% critical value for a
    chi-square with 1 degree of freedom is 3.841.
    """
    x = np.asarray(exceptions, dtype=int)
    n = len(x)
    k = int(np.sum(x))
    if n == 0:
        raise ValueError("no observations")
    p_hat = k / n
    if k == 0:
        ll_alt = 0.0  # (1 - 0)^n
        ll_null = n * math.log(1.0 - alpha)
        stat = -2.0 * (ll_null - ll_alt)
        return float(stat), bool(stat > 3.841)
    if k == n:
        ll_alt = n * math.log(p_hat)
        ll_null = n * math.log(alpha)
        stat = -2.0 * (ll_null - ll_alt)
        return float(stat), bool(stat > 3.841)
    ll_null = (n - k) * math.log(1 - alpha) + k * math.log(alpha)
    ll_alt = (n - k) * math.log(1 - p_hat) + k * math.log(p_hat)
    stat = -2.0 * (ll_null - ll_alt)
    return float(stat), bool(stat > 3.841)


def christoffersen_independence(exceptions):
    """Christoffersen independence test on the exception sequence.

    Returns (statistic, reject_at_5pct). Counts 00/01/10/11 transitions;
    a clustered breach pattern rejects independence.
    """
    x = np.asarray(exceptions, dtype=int)
    if len(x) < 3:
        return 0.0, False
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(x[:-1], x[1:]):
        if a == 0 and b == 0:
            n00 += 1
        elif a == 0 and b == 1:
            n01 += 1
        elif a == 1 and b == 0:
            n10 += 1
        else:
            n11 += 1
    n0 = n00 + n01
    n1 = n10 + n11
    if n0 == 0 or n1 == 0:
        return 0.0, False
    p01 = n01 / n0 if n0 else 0.0
    p11 = n11 / n1 if n1 else 0.0
    p = (n01 + n11) / (n0 + n1)
    ll_null = 0.0
    if 0 < p < 1:
        ll_null = (n00 + n10) * math.log(1 - p) + (n01 + n11) * math.log(p)
    ll_alt = 0.0
    for count, prob in ((n00, 1 - p01), (n01, p01), (n10, 1 - p11), (n11, p11)):
        if count and 0 < prob < 1:
            ll_alt += count * math.log(prob)
    stat = -2.0 * (ll_null - ll_alt)
    return float(stat), bool(stat > 3.841)


def backtest_var(returns, var_series, alpha=0.05):
    """Full VaR backtest summary for a returns / VaR-forecast pair."""
    exc = count_exceptions(returns, var_series)
    n = len(exc)
    k = int(exc.sum())
    kupiec_stat, kupiec_reject = kupiec_pof(exc, alpha)
    chris_stat, chris_reject = christoffersen_independence(exc)
    return {
        "n_observations": n,
        "exceptions": k,
        "expected_exceptions": round(alpha * n, 2),
        "breach_rate": round(k / n, 4) if n else 0.0,
        "kupiec_statistic": round(kupiec_stat, 3),
        "kupiec_reject_5pct": kupiec_reject,
        "christoffersen_statistic": round(chris_stat, 3),
        "christoffersen_reject_5pct": chris_reject,
        "passed": (not kupiec_reject) and (not chris_reject),
    }
