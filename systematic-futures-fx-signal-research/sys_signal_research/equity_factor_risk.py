"""Equity factor-risk analytics in the style of Axioma-style risk models.

The module answers the questions a portfolio-management risk analyst
asks every morning: what factor tilts does the book carry, how much
active risk (tracking error) sits against the benchmark, where does
total risk come from (factors vs stock-specific), and is the risk model
itself still trustworthy? It mirrors the workflow of the JPMorgan
Equity Portfolio Management / Model Risk Management role: apply a
factor risk model, monitor exposures and concentrations, and run
model-governance checks on the model before anyone acts on it.

All data is synthetic and seeded, like the rest of this project: stock
returns are generated from known factor betas plus idiosyncratic noise,
so the estimator can be checked against ground truth. No real market
data, no real Axioma data, and nothing here claims to reproduce any
commercial risk model.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252

FACTORS = ["Market", "Size", "Value", "Momentum", "Quality"]

# Annualised factor volatility used to simulate factor returns.
FACTOR_VOLS = {"Market": 0.16, "Size": 0.06, "Value": 0.07, "Momentum": 0.09, "Quality": 0.05}

SECTORS = ["Technology", "Financials", "Health Care", "Industrials", "Consumer", "Energy"]


def generate_equity_panel(seed=42, n_stocks=40, n_days=504):
    """Generate a synthetic equity panel with known factor structure.

    Returns ``(stock_returns, factor_returns, true_betas, sectors)``:
    daily stock returns, daily factor returns, the true betas used to
    build the stocks, and a sector label per stock. Factor returns are
    mildly correlated (market correlates with the style factors); each
    stock loads mostly on the market plus a random tilt on two style
    factors, then idiosyncratic noise. Seeded, so results reproduce.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-02", periods=n_days)
    corr = np.eye(len(FACTORS))
    corr[0, 1:] = corr[1:, 0] = 0.25  # market correlates with style factors
    vols = np.array([FACTOR_VOLS[f] for f in FACTORS]) / np.sqrt(TRADING_DAYS)
    cov = np.outer(vols, vols) * corr
    factor_rets = rng.multivariate_normal(np.zeros(len(FACTORS)), cov, size=n_days)
    factor_returns = pd.DataFrame(factor_rets, index=index, columns=FACTORS)

    stocks = [f"STK{i:02d}" for i in range(n_stocks)]
    true_betas = pd.DataFrame(0.0, index=stocks, columns=FACTORS)
    true_betas["Market"] = rng.uniform(0.7, 1.3, size=n_stocks)
    for i in range(n_stocks):
        styles = rng.choice(FACTORS[1:], size=2, replace=False)
        true_betas.loc[stocks[i], styles] = rng.uniform(-0.8, 0.8, size=2)
    idio_vol = rng.uniform(0.15, 0.35, size=n_stocks) / np.sqrt(TRADING_DAYS)
    idio = rng.standard_normal((n_days, n_stocks)) * idio_vol
    stock_rets = factor_rets @ true_betas.values.T + idio
    stock_returns = pd.DataFrame(stock_rets, index=index, columns=stocks)
    sectors = pd.Series(
        [SECTORS[i % len(SECTORS)] for i in range(n_stocks)], index=stocks, name="sector"
    )
    return stock_returns, factor_returns, true_betas, sectors


def estimate_factor_betas(stock_returns, factor_returns):
    """Estimate factor betas per stock by OLS with an intercept.

    Aligns the two frames on their shared dates and drops rows with
    missing values. Returns a dict with ``betas`` (stocks x factors),
    ``alpha`` (daily, per stock), ``r_squared``, ``residual_std`` and
    ``residuals`` (daily residual returns). A stock with fewer than
    60 usable observations is skipped rather than fitted on nothing.
    """
    aligned = stock_returns.join(factor_returns, how="inner")
    factors = aligned[factor_returns.columns]
    stocks = aligned[stock_returns.columns].dropna(how="all", axis=1)
    x = np.column_stack([np.ones(len(factors)), factors.values])
    betas, alpha, r2, resid_std, residuals = {}, {}, {}, {}, {}
    for name in stocks.columns:
        y = stocks[name].values
        mask = np.isfinite(y) & np.all(np.isfinite(x), axis=1)
        if mask.sum() < 60:
            continue
        coef, *_ = np.linalg.lstsq(x[mask], y[mask], rcond=None)
        fitted = x[mask] @ coef
        resid = y[mask] - fitted
        ss_tot = np.sum((y[mask] - y[mask].mean()) ** 2)
        betas[name] = coef[1:]
        alpha[name] = coef[0]
        r2[name] = 1.0 - float(np.sum(resid**2) / ss_tot) if ss_tot > 0 else 0.0
        resid_std[name] = float(np.std(resid, ddof=1))
        residuals[name] = pd.Series(resid, index=stocks.index[mask])
    return {
        "betas": pd.DataFrame(betas, index=factor_returns.columns).T,
        "alpha": pd.Series(alpha),
        "r_squared": pd.Series(r2),
        "residual_std": pd.Series(resid_std),
        "residuals": pd.DataFrame(residuals),
    }


def tracking_error(portfolio_returns, benchmark_returns, annualised=True):
    """Annualised tracking error: volatility of active returns.

    Active return is the portfolio return minus the benchmark return on
    shared dates. Returns 0.0 when the two series are identical, and
    NaN when there are fewer than 2 shared dates.
    """
    p, b = portfolio_returns.align(benchmark_returns, join="inner")
    active = (p - b).dropna()
    if len(active) < 2:
        return float("nan")
    te = float(active.std(ddof=1))
    return te * np.sqrt(TRADING_DAYS) if annualised else te


def factor_risk_decomposition(weights, betas, factor_cov, idio_var):
    """Split portfolio variance into factor risk and specific risk.

    ``weights`` is a Series of portfolio weights indexed by stock,
    ``betas`` the stock x factor matrix, ``factor_cov`` the annualised
    factor covariance, and ``idio_var`` annualised idiosyncratic
    variance per stock. Returns portfolio factor exposures, the
    variance split, annualised total/factor/specific volatility, and
    each factor's share of factor variance.
    """
    w = np.asarray(weights.reindex(betas.index).fillna(0.0), dtype=float)
    w = w / w.sum() if w.sum() != 0 else w
    exposures = betas.values.T @ w
    factor_var = float(exposures @ factor_cov.values @ exposures)
    specific_var = float(np.sum((w**2) * np.asarray(idio_var.reindex(betas.index).fillna(0.0))))
    total_var = factor_var + specific_var
    contrib = exposures * (factor_cov.values @ exposures)
    return {
        "factor_exposures": pd.Series(exposures, index=betas.columns),
        "factor_variance": factor_var,
        "specific_variance": specific_var,
        "total_variance": total_var,
        "total_vol": float(np.sqrt(max(total_var, 0.0))),
        "factor_vol": float(np.sqrt(max(factor_var, 0.0))),
        "specific_vol": float(np.sqrt(max(specific_var, 0.0))),
        "factor_risk_contribution": pd.Series(contrib, index=betas.columns),
    }


def portfolio_risk_summary(weights, stock_returns, factor_returns, betas, benchmark_returns=None, sectors=None):
    """One-page risk summary for a portfolio, in the PM-report style.

    Combines the factor decomposition with tracking error against the
    benchmark (when given), concentration (Herfindahl index of weights
    and the largest positions), and sector exposures. Volatilities are
    annualised. The benchmark defaults to the equal-weighted stock
    universe when no benchmark series is supplied.
    """
    w = pd.Series(weights).reindex(betas.index).fillna(0.0)
    w = w / w.sum()
    est = estimate_factor_betas(stock_returns, factor_returns)
    factor_cov = factor_returns.cov() * TRADING_DAYS
    idio_var = (est["residual_std"] ** 2) * TRADING_DAYS
    decomp = factor_risk_decomposition(w, betas, factor_cov, idio_var)
    port_rets = (stock_returns[betas.index] @ w).dropna()
    if benchmark_returns is None:
        benchmark_returns = stock_returns[betas.index].mean(axis=1)
    te = tracking_error(port_rets, benchmark_returns)
    summary = {
        **{k: v for k, v in decomp.items() if k != "factor_risk_contribution"},
        "factor_risk_contribution": {
            k: round(float(v), 6) for k, v in decomp["factor_risk_contribution"].items()
        },
        "tracking_error": te,
        "top_factor_tilts": {
            k: round(float(v), 4)
            for k, v in decomp["factor_exposures"].reindex(
                decomp["factor_exposures"].abs().sort_values(ascending=False).index
            )[:3].items()
        },
        "concentration_hhi": float(np.sum(w.values**2)),
        "largest_positions": {k: round(float(v), 4) for k, v in w.sort_values(ascending=False)[:5].items()},
        "n_positions": int((w != 0).sum()),
    }
    if sectors is not None:
        summary["sector_exposures"] = {
            k: round(float(v), 4) for k, v in w.groupby(sectors.reindex(w.index)).sum().items()
        }
    return summary


def governance_checks(stock_returns, factor_returns, betas, r_squared, residuals):
    """Model-governance checks on the factor risk model itself.

    Each check returns ``{"check", "status", "detail"}`` with status
    ``pass``, ``warn`` or ``fail``. The checks mirror SR 11-7 style
    validation: missing data, stale (constant) factors, low explanatory
    power, autocorrelated residuals, unstable betas across halves of
    the sample, and collinear factors. A model that fails a check
    should not be relied on for risk limits until it is fixed.
    """
    checks = []
    missing = float(stock_returns.isna().mean().mean())
    checks.append(
        {
            "check": "missing_data",
            "status": "pass" if missing == 0 else ("warn" if missing < 0.01 else "fail"),
            "detail": f"{missing:.2%} of stock-return cells are missing",
        }
    )
    stale = [f for f in factor_returns.columns if factor_returns[f].nunique() <= 1]
    checks.append(
        {
            "check": "stale_factors",
            "status": "fail" if stale else "pass",
            "detail": f"constant factors: {stale}" if stale else "no constant factor series",
        }
    )
    low_r2 = float((r_squared < 0.20).mean()) if len(r_squared) else 1.0
    checks.append(
        {
            "check": "low_explanatory_power",
            "status": "pass" if low_r2 < 0.25 else ("warn" if low_r2 < 0.50 else "fail"),
            "detail": f"{low_r2:.0%} of stocks have R-squared below 0.20 (median {float(r_squared.median()):.2f})",
        }
    )
    dw_values = []
    for name in residuals.columns:
        r = residuals[name].dropna().values
        if len(r) > 10:
            dw_values.append(float(np.sum(np.diff(r) ** 2) / np.sum(r**2)))
    dw = float(np.median(dw_values)) if dw_values else float("nan")
    checks.append(
        {
            "check": "residual_autocorrelation",
            "status": "pass" if 1.5 <= dw <= 2.5 else "warn",
            "detail": f"median Durbin-Watson statistic {dw:.2f} (2.0 means no autocorrelation)",
        }
    )
    half = len(factor_returns) // 2
    first = estimate_factor_betas(stock_returns.iloc[:half], factor_returns.iloc[:half])["betas"]
    second = estimate_factor_betas(stock_returns.iloc[half:], factor_returns.iloc[half:])["betas"]
    common = first.index.intersection(second.index)
    if len(common) >= 5:
        corr = float(np.corrcoef(first.loc[common].values.ravel(), second.loc[common].values.ravel())[0, 1])
    else:
        corr = float("nan")
    checks.append(
        {
            "check": "beta_stability",
            "status": "pass" if corr >= 0.7 else ("warn" if corr >= 0.4 else "fail"),
            "detail": f"split-half beta correlation {corr:.2f}",
        }
    )
    factor_corr = factor_returns.corr().abs().to_numpy(copy=True)
    np.fill_diagonal(factor_corr, 0.0)
    finite = factor_corr[np.isfinite(factor_corr)]
    max_corr = float(finite.max()) if finite.size else float("nan")
    checks.append(
        {
            "check": "factor_collinearity",
            "status": "warn" if not np.isfinite(max_corr) else ("pass" if max_corr < 0.8 else "warn"),
            "detail": (
                "a factor correlation is undefined (constant factor?)"
                if not np.isfinite(max_corr)
                else f"largest absolute factor correlation {max_corr:.2f}"
            ),
        }
    )
    return checks
