"""Portfolio construction: combine strategy backtests into one book."""

import numpy as np
import pandas as pd

from .backtest import risk_parity_weights


def build_portfolio(strategy_results, weights=None):
    """Combine per-strategy backtest DataFrames into one portfolio.

    ``strategy_results`` maps strategy name -> backtest DataFrame (the
    output of :func:`backtest.backtest`). When ``weights`` is omitted,
    equal-risk-contribution weights are computed from the covariance of
    the strategies' daily returns. Returns (portfolio returns Series,
    weights Series).
    """
    rets = pd.DataFrame({name: df["return"] for name, df in strategy_results.items()})
    rets = rets.fillna(0.0)
    if weights is None:
        cov = rets.cov().values * 252
        w = risk_parity_weights(cov)
        weights = pd.Series(w, index=rets.columns)
    else:
        weights = pd.Series(weights).reindex(rets.columns).fillna(0.0)
        weights = weights / weights.sum()
    port_rets = rets @ weights
    return port_rets, weights
