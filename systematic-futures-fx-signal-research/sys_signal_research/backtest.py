"""Backtesting engine and portfolio construction.

The backtester applies positions with a one-day lag, charges a cost
per unit of turnover, and can scale positions to a volatility target.
Portfolio construction weights whole signal strategies (not single
names) by equal risk contribution, and metrics summarise the resulting
equity curve.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252


def backtest(prices, positions, cost_bps=2.0):
    """Backtest one position series against one price series.

    ``positions`` is applied from the next day's open (lag 1), so no
    look-ahead. Cost is ``cost_bps`` basis points of notional per unit
    of absolute position change. Returns a DataFrame with daily
    strategy returns, gross returns, costs, turnover and equity curve.
    """
    rets = prices.pct_change()
    pos = positions.reindex(prices.index).fillna(0.0)
    applied = pos.shift(1).fillna(0.0)
    turnover = applied.diff().abs().fillna(0.0)
    gross = applied * rets
    cost = turnover * (cost_bps / 10_000.0)
    strat = (gross - cost).fillna(0.0)
    equity = (1.0 + strat).cumprod()
    return pd.DataFrame(
        {
            "return": strat,
            "gross_return": gross.fillna(0.0),
            "cost": cost.fillna(0.0),
            "turnover": turnover,
            "position": applied,
            "equity": equity,
        }
    )


def vol_target_scale(returns, target_vol=0.10, window=60):
    """Scale factor that targets ``target_vol`` annualised volatility.

    Uses the trailing ``window``-day realised volatility of the return
    series, capped at 3x leverage and floored at 0, so a strategy that
    is running hot is scaled down before the next day's trade.
    """
    realised = returns.rolling(window, min_periods=window).std() * np.sqrt(TRADING_DAYS)
    scale = target_vol / realised.replace(0, np.nan)
    return scale.clip(0, 3.0).fillna(0.0)


def apply_vol_target(positions, returns, target_vol=0.10, window=60):
    """Scale a position series by the vol-target factor, lagged one day."""
    scale = vol_target_scale(returns, target_vol=target_vol, window=window)
    scale = scale.reindex(positions.index)
    return (positions * scale.shift(1).fillna(0.0)).clip(-3, 3)


def risk_parity_weights(cov, max_iter=500):
    """Equal-risk-contribution weights for a covariance matrix.

    Minimises the squared gap between each asset's risk contribution
    and the average contribution, subject to weights summing to one
    and staying non-negative. Falls back to inverse-volatility weights
    if the optimiser fails.
    """
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    vols = np.sqrt(np.diag(cov))
    if np.any(vols <= 0) or not np.all(np.isfinite(cov)):
        return np.ones(n) / n
    x0 = (1.0 / vols) / np.sum(1.0 / vols)

    def objective(w):
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol <= 0:
            return 1e6
        contrib = w * (cov @ w) / port_vol
        target = port_vol / n
        return float(np.sum((contrib - target) ** 2))

    res = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
        options={"maxiter": max_iter},
    )
    if res.success and np.all(np.isfinite(res.x)) and res.x.sum() > 0:
        return res.x / res.x.sum()
    return x0


def portfolio_metrics(equity):
    """Performance and risk summary of an equity curve (Series)."""
    equity = equity.dropna()
    rets = equity.pct_change().dropna()
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
    years = len(rets) / TRADING_DAYS
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    vol = float(rets.std() * np.sqrt(TRADING_DAYS)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(TRADING_DAYS)) if rets.std() > 0 else 0.0
    downside = rets[rets < 0]
    sortino = (
        float(rets.mean() / downside.std() * np.sqrt(TRADING_DAYS))
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    return {
        "total_return": total,
        "cagr": cagr,
        "annual_vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "n_days": int(len(rets)),
    }


def diversification_stats(strategy_returns):
    """Correlation structure across strategy return series.

    Returns the average pairwise correlation and the worst (largest)
    single correlation, which is what limits diversification benefit
    when signals are combined into one portfolio.
    """
    corr = strategy_returns.corr()
    vals = corr.values[np.triu_indices_from(corr.values, k=1)]
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return {"avg_correlation": 0.0, "max_correlation": 0.0}
    return {
        "avg_correlation": float(np.mean(vals)),
        "max_correlation": float(np.max(vals)),
    }
