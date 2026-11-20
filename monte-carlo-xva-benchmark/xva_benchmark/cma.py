"""Stochastic projection and capital market assumptions (CMA).

Extension of the Monte-Carlo XVA Benchmark Framework for portfolio
construction and strategic asset allocation work:

1. **Building-block expected returns** -- a forward-looking return is the
   sum of its building blocks (cash yield, inflation, real growth and a
   risk premium), instead of a backward-looking historical average.
2. **Bayesian capital market assumptions** -- historical sample means are
   combined with a prior view through normal-normal conjugacy, so the
   posterior expected return sits between the prior and the sample and
   moves toward the sample as the history lengthens. Sample correlations
   are shrunk toward a structured target (Ledoit-Wolf style) so the
   resulting matrix stays well conditioned.
3. **Private-market stochastic projection** -- NAV paths for a private fund
   or vehicle, simulated with GBM growth plus scheduled capital calls
   (money in) and distributions (money out), with NAV floored at zero.
4. **Tail risk** -- value-at-risk and conditional value-at-risk (expected
   shortfall) on terminal outcomes, for climate / stress scenario review.

Everything is numpy only, seeded and reproducible, matching the style of
the rest of the framework. Figures here are illustrative inputs, not
market forecasts.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Building-block expected returns
# ---------------------------------------------------------------------------

def building_block_expected_return(cash_yield: float, inflation: float,
                                   real_growth: float,
                                   risk_premium: float) -> float:
    """Forward-looking expected return as the sum of its building blocks.

    E[R] = cash yield + inflation + real growth + risk premium.
    """
    return float(cash_yield + inflation + real_growth + risk_premium)


# ---------------------------------------------------------------------------
# Bayesian capital market assumptions
# ---------------------------------------------------------------------------

def bayesian_posterior_mean(prior_mean, prior_var, sample_mean,
                            sample_var, n_obs: int):
    """Normal-normal posterior for the expected return of each asset.

    Prior:      mu ~ N(prior_mean, prior_var)
    Likelihood: sample_mean | mu ~ N(mu, sample_var / n_obs)
    Posterior mean is a precision-weighted average of prior and sample;
    posterior variance is smaller than either input variance.
    """
    prior_mean = np.asarray(prior_mean, dtype=float)
    prior_var = np.asarray(prior_var, dtype=float)
    sample_mean = np.asarray(sample_mean, dtype=float)
    sample_var = np.asarray(sample_var, dtype=float)
    if n_obs <= 0:
        raise ValueError("n_obs must be positive")
    if np.any(prior_var <= 0) or np.any(sample_var <= 0):
        raise ValueError("variances must be positive")
    prior_prec = 1.0 / prior_var
    like_prec = n_obs / sample_var
    post_var = 1.0 / (prior_prec + like_prec)
    post_mean = post_var * (prior_mean * prior_prec
                            + sample_mean * like_prec)
    return post_mean, post_var


def shrinkage_correlation(sample_corr: np.ndarray,
                          shrinkage: float = 0.25,
                          target: str = "identity") -> np.ndarray:
    """Shrink a sample correlation matrix toward a structured target.

    R_shrunk = (1 - delta) * R_sample + delta * R_target, with delta in
    [0, 1]. Targets: "identity" (uncorrelated) or "constant" (single common
    off-diagonal correlation, the average of the sample off-diagonals).
    The diagonal stays exactly 1.
    """
    corr = np.asarray(sample_corr, dtype=float)
    if corr.ndim != 2 or corr.shape[0] != corr.shape[1]:
        raise ValueError("sample_corr must be a square matrix")
    if not 0.0 <= shrinkage <= 1.0:
        raise ValueError("shrinkage must be in [0, 1]")
    n = corr.shape[0]
    if target == "identity":
        tgt = np.eye(n)
    elif target == "constant":
        off = corr[~np.eye(n, dtype=bool)]
        avg = float(off.mean()) if off.size else 0.0
        tgt = np.full((n, n), avg)
        np.fill_diagonal(tgt, 1.0)
    else:
        raise ValueError("target must be 'identity' or 'constant'")
    shrunk = (1.0 - shrinkage) * corr + shrinkage * tgt
    np.fill_diagonal(shrunk, 1.0)
    return shrunk


def cma_from_history(returns: np.ndarray, prior_means, prior_vols,
                     shrinkage: float = 0.25) -> dict:
    """Forward-looking capital market assumptions from a return history.

    Args:
        returns:      (n_obs, n_assets) historical returns.
        prior_means:  prior expected return per asset.
        prior_vols:   prior standard deviation of the expected return.
        shrinkage:    correlation shrinkage intensity toward identity.

    Returns a dict with posterior expected returns, posterior volatilities
    (sample vols, unchanged by the mean update), the shrunk correlation
    matrix and the implied covariance matrix.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        raise ValueError("returns must be a 2-D array (n_obs, n_assets)")
    n_obs = returns.shape[0]
    sample_mean = returns.mean(axis=0)
    sample_var = returns.var(axis=0, ddof=1)
    post_mean, post_var = bayesian_posterior_mean(
        prior_means, np.asarray(prior_vols, dtype=float) ** 2,
        sample_mean, sample_var, n_obs)
    sample_corr = np.corrcoef(returns, rowvar=False)
    sample_corr = np.atleast_2d(sample_corr)
    shrunk_corr = shrinkage_correlation(sample_corr, shrinkage)
    vols = np.sqrt(sample_var)
    cov = np.outer(vols, vols) * shrunk_corr
    return {
        "expected_returns": post_mean,
        "posterior_std": np.sqrt(post_var),
        "volatilities": vols,
        "correlation": shrunk_corr,
        "covariance": cov,
        "n_obs": n_obs,
    }


# ---------------------------------------------------------------------------
# Private-market stochastic projection (NAV and cash flows)
# ---------------------------------------------------------------------------

def simulate_private_nav(initial_nav: float, expected_return: float,
                         volatility: float, times: np.ndarray,
                         n_paths: int, rng: np.random.Generator,
                         capital_calls: dict | None = None,
                         distributions: dict | None = None) -> dict:
    """Simulate private-fund NAV paths with calls and distributions.

    NAV follows GBM between grid dates. At a grid date ``t`` a scheduled
    capital call adds cash to NAV and a distribution removes cash from NAV
    (NAV is floored at zero after each event). ``capital_calls`` and
    ``distributions`` map a time-grid index to a cash amount per path.

    Returns a dict with ``nav`` paths (n_paths, len(times)), ``net_cash_flow``
    per path and grid date (calls negative, distributions positive, from the
    investor's point of view), and totals.
    """
    times = np.asarray(times, dtype=float)
    n_steps = len(times) - 1
    if n_steps < 1:
        raise ValueError("times must contain at least two grid points")
    if initial_nav < 0 or volatility < 0:
        raise ValueError("initial_nav and volatility must be non-negative")
    calls = dict(capital_calls or {})
    dists = dict(distributions or {})
    dt = np.diff(times)
    z = rng.standard_normal((n_paths, n_steps))
    log_increments = ((expected_return - 0.5 * volatility ** 2) * dt
                      + volatility * np.sqrt(dt) * z)
    nav = np.empty((n_paths, len(times)))
    nav[:, 0] = float(initial_nav)
    cash_flow = np.zeros((n_paths, len(times)))
    for i in range(n_steps):
        nav[:, i + 1] = nav[:, i] * np.exp(log_increments[:, i])
        idx = i + 1
        if idx in calls:
            nav[:, idx] += float(calls[idx])
            cash_flow[:, idx] -= float(calls[idx])
        if idx in dists:
            paid = np.minimum(nav[:, idx], float(dists[idx]))
            nav[:, idx] -= paid
            cash_flow[:, idx] += paid
        nav[:, idx] = np.maximum(nav[:, idx], 0.0)
    return {
        "nav": nav,
        "net_cash_flow": cash_flow,
        "total_calls": float(sum(calls.values())),
        "total_distributions": float(sum(dists.values())),
    }


def project_cash_flows(initial_nav: float, expected_return: float,
                       volatility: float, times: np.ndarray,
                       n_paths: int, seed: int = 42,
                       capital_calls: dict | None = None,
                       distributions: dict | None = None) -> dict:
    """Seeded wrapper around :func:`simulate_private_nav` for one-liners."""
    rng = np.random.default_rng(seed)
    return simulate_private_nav(initial_nav, expected_return, volatility,
                                times, n_paths, rng,
                                capital_calls=capital_calls,
                                distributions=distributions)


# ---------------------------------------------------------------------------
# Tail risk (VaR / CVaR)
# ---------------------------------------------------------------------------

def tail_risk(values, confidence: float = 0.95) -> dict:
    """VaR and CVaR (expected shortfall) of terminal outcomes.

    ``values`` are terminal values (e.g. NAV or portfolio value) and the
    reference is their mean: loss = mean(value) - value. VaR is the
    ``confidence`` quantile of the loss distribution; CVaR is the mean loss
    beyond VaR. Both are reported as non-negative amounts.
    """
    values = np.asarray(values, dtype=float).ravel()
    if values.size == 0:
        raise ValueError("values must be non-empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    losses = values.mean() - values
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    cvar = float(tail.mean()) if tail.size else var
    return {
        "var": max(var, 0.0),
        "cvar": max(cvar, 0.0),
        "confidence": confidence,
        "mean_value": float(values.mean()),
    }
