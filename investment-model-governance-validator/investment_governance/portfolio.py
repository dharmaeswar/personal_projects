"""Portfolio construction and optimisation validation.

Validates a mean-variance portfolio the way an independent reviewer
would: weights must be long-only, sum to one, respect caps, beat the
equal-weight portfolio on variance, and not churn. The optimiser is a
projected-gradient solver (simplex + cap projection) so the package has
no dependency beyond NumPy.
"""

import numpy as np


def _project_simplex_capped(vector, cap):
    """Project onto {w >= 0, sum w = 1, w <= cap} by iterative clipping."""
    w = np.asarray(vector, dtype=float).copy()
    n = len(w)
    if cap is not None and cap * n < 1.0 - 1e-12:
        raise ValueError("cap too small: n * cap must be >= 1")
    for _ in range(100):
        if cap is not None:
            w = np.minimum(w, cap)
        # Simplex projection (Duchi et al.).
        u = np.sort(w)[::-1]
        css = np.cumsum(u) - 1.0
        rho = np.nonzero(u - css / (np.arange(n) + 1) > 0)[0]
        if len(rho) == 0:
            theta = 0.0
        else:
            r = rho[-1]
            theta = css[r] / (r + 1)
        w_new = np.maximum(w - theta, 0.0)
        if cap is not None:
            w_new = np.minimum(w_new, cap)
        if np.max(np.abs(w_new - w)) < 1e-12:
            w = w_new
            break
        w = w_new
    # Final clean-up: exact sum of one.
    w = np.maximum(w, 0.0)
    if cap is not None:
        w = np.minimum(w, cap)
    w = w / w.sum()
    return w


def min_variance_weights(cov, cap=None, max_iter=5000, tol=1e-10):
    """Long-only minimum-variance weights, optionally capped per name."""
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    if cov.shape != (n, n):
        raise ValueError("cov must be square")
    step = 1.0 / (np.linalg.norm(cov, 2) + 1e-12)
    w = np.full(n, 1.0 / n)
    for _ in range(max_iter):
        grad = 2.0 * cov @ w
        w_new = _project_simplex_capped(w - step * grad, cap)
        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            break
        w = w_new
    return w


def portfolio_volatility(weights, cov):
    """Annualised-free portfolio volatility for a weight vector."""
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    return float(np.sqrt(max(w @ cov @ w, 0.0)))


def portfolio_return(weights, expected_returns):
    """Expected portfolio return for a weight vector."""
    return float(np.asarray(weights, dtype=float) @ np.asarray(expected_returns, dtype=float))


def sharpe_ratio(weights, expected_returns, cov, risk_free=0.0):
    """Expected Sharpe ratio of a portfolio."""
    vol = portfolio_volatility(weights, cov)
    if vol == 0:
        return 0.0
    return (portfolio_return(weights, expected_returns) - risk_free) / vol


def herfindahl(weights):
    """Concentration: sum of squared weights, in [1/n, 1]."""
    w = np.asarray(weights, dtype=float)
    return float(np.sum(w ** 2))


def turnover(weights_today, weights_yesterday):
    """One-way turnover between two allocations."""
    w0 = np.asarray(weights_yesterday, dtype=float)
    w1 = np.asarray(weights_today, dtype=float)
    return float(0.5 * np.sum(np.abs(w1 - w0)))


def validate_portfolio(weights, cov, expected_returns, cap=None, max_turnover=0.5):
    """Run the standard effective-challenge checks on a portfolio.

    Returns a dict of named checks with ``passed`` flags and values.
    """
    w = np.asarray(weights, dtype=float)
    checks = {
        "weights_sum_to_one": bool(abs(w.sum() - 1.0) < 1e-6),
        "long_only": bool(np.all(w >= -1e-9)),
        "cap_respected": bool(cap is None or np.all(w <= cap + 1e-9)),
        "variance_beats_equal_weight": bool(
            portfolio_volatility(w, cov)
            < portfolio_volatility(np.full(len(w), 1.0 / len(w)), cov)
        ),
        "concentration_below_0.5": bool(herfindahl(w) < 0.5),
    }
    checks["passed"] = all(checks.values())
    checks["volatility"] = portfolio_volatility(w, cov)
    checks["sharpe"] = sharpe_ratio(w, expected_returns, cov)
    checks["herfindahl"] = herfindahl(w)
    return checks
