"""Cross-sectional equity alpha-signal research.

The module answers the questions a systematic-equities researcher asks
about a new alpha idea: does the signal predict returns out of sample,
how strong is the information coefficient, does the edge survive costs
and delayed execution, and does a long-short book built on it earn a
positive risk-adjusted return?

It mirrors the Cubist / Point72 Quantitative Researcher workflow:
hypothesis (a characteristic should predict returns), signal
construction from point-in-time data only, information-coefficient
analysis, and a cost-aware long-short backtest with turnover and
signal-decay diagnostics.

All data is synthetic and seeded, like the rest of this project. Stock
returns are built from a known structure: each stock carries a
persistent drift component tied to its value and quality
characteristics plus a stock-specific drift, a market factor, and
idiosyncratic noise. The drift is deliberately strong (about 22%
annual cross-sectional dispersion) so that a two-year, 40-stock panel
can detect it — the point is to exercise the research tooling, not to
claim a tradable edge. The signals therefore have a real (seeded) edge
to discover, and the research tools have to recover it — nothing here
uses real market data or claims a live return.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def generate_equity_alpha_panel(seed=7, n_stocks=40, n_days=504):
    """Generate a synthetic equity panel with known alpha structure.

    Returns ``(prices, characteristics)`` where ``prices`` is a
    DataFrame of daily closing prices (``n_days`` x ``n_stocks``) and
    ``characteristics`` is a DataFrame with one row per stock holding
    the point-in-time value (book-to-price) and quality (profitability)
    characteristics plus the true drift used to build the returns.

    Daily returns are ``drift + beta * market + idiosyncratic noise``,
    with ``drift`` a mix of a value tilt, a quality tilt and a
    stock-specific component, so value, quality and (through past
    returns) momentum signals all carry genuine predictive content.
    Seeded, so results reproduce.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-02", periods=n_days)
    stocks = [f"STK{i:02d}" for i in range(n_stocks)]

    value = rng.normal(0.0, 1.0, size=n_stocks)
    quality = rng.normal(0.0, 1.0, size=n_stocks)
    stock_specific = rng.normal(0.0, 1.0, size=n_stocks)
    # Annualised drift: value and quality tilts plus a stock-specific part.
    # The drift is deliberately strong (about 22% annual cross-sectional
    # dispersion) so that a two-year, 40-stock panel can detect it — the
    # point is to exercise the research tooling, not to claim a tradable
    # edge. See the README.
    drift_annual = 0.12 * value + 0.10 * quality + 0.15 * stock_specific
    drift_daily = drift_annual / TRADING_DAYS

    betas = rng.uniform(0.7, 1.3, size=n_stocks)
    market = rng.normal(0.06 / TRADING_DAYS, 0.16 / np.sqrt(TRADING_DAYS), size=n_days)
    idio_vol = rng.uniform(0.10, 0.20, size=n_stocks) / np.sqrt(TRADING_DAYS)
    idio = rng.standard_normal((n_days, n_stocks)) * idio_vol
    rets = drift_daily + np.outer(market, betas) + idio
    returns = pd.DataFrame(rets, index=index, columns=stocks)
    prices = (1.0 + returns).cumprod() * 100.0

    characteristics = pd.DataFrame(
        {
            "value": value,
            "quality": quality,
            "true_drift_annual": drift_annual,
            "beta": betas,
        },
        index=stocks,
    )
    return prices, characteristics


def _zscore_cross_section(frame):
    """Z-score each row (each day) across stocks, NaN-safe."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0).fillna(0.0)


def cross_sectional_momentum(prices, lookback=252, skip=21):
    """12-1 momentum: trailing return skipping the most recent month.

    The signal at day ``t`` uses prices up to ``t - skip`` only, so it
    is point-in-time. Each day's cross-section is z-scored.
    """
    ret = prices.shift(skip) / prices.shift(lookback + skip) - 1.0
    return _zscore_cross_section(ret)


def value_signal(characteristics):
    """Value signal: book-to-price characteristic, z-scored across stocks."""
    return pd.Series(characteristics["value"].values, index=characteristics.index)


def quality_signal(characteristics):
    """Quality signal: profitability characteristic, z-scored across stocks."""
    return pd.Series(characteristics["quality"].values, index=characteristics.index)


def combine_signals(signals, weights=None):
    """Combine daily cross-sectional signals into one composite signal.

    ``signals`` is a list of DataFrames (days x stocks) or Series
    (stocks, broadcast across every day of the first signal). Weights
    default to equal. The composite is z-scored each day.
    """
    if weights is None:
        weights = [1.0 / len(signals)] * len(signals)
    base = signals[0]
    total = pd.DataFrame(0.0, index=base.index, columns=base.columns)
    for signal, weight in zip(signals, weights):
        if isinstance(signal, pd.Series):
            aligned = pd.DataFrame(
                np.tile(signal.values, (len(base), 1)),
                index=base.index,
                columns=base.columns,
            )
        else:
            aligned = signal.reindex(index=base.index, columns=base.columns).fillna(0.0)
        total = total + weight * aligned
    return _zscore_cross_section(total)


def information_coefficient(signal, forward_returns, lag=1):
    """Rank information coefficient of a signal vs forward returns.

    ``signal`` is a DataFrame (days x stocks), ``forward_returns`` the
    same-shaped daily returns. The signal at day ``t`` is compared
    with the return at ``t + lag``. Returns a dict with the mean daily
    rank IC, its standard deviation, t-statistic, hit rate (share of
    days with positive IC) and the number of days used.
    """
    aligned_signal = signal.shift(0)
    fwd = forward_returns.shift(-lag)
    daily_ic = []
    for day in signal.index:
        s = aligned_signal.loc[day]
        r = fwd.loc[day]
        both = pd.concat([s, r], axis=1).dropna()
        if len(both) < 5:
            continue
        ic = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank(), method="pearson")
        if pd.notna(ic):
            daily_ic.append(ic)
    daily_ic = np.asarray(daily_ic, dtype=float)
    n = len(daily_ic)
    mean_ic = float(daily_ic.mean()) if n else float("nan")
    std_ic = float(daily_ic.std(ddof=1)) if n > 1 else float("nan")
    t_stat = float(mean_ic / (std_ic / np.sqrt(n))) if n > 1 and std_ic > 0 else float("nan")
    return {
        "mean_ic": mean_ic,
        "ic_std": std_ic,
        "t_stat": t_stat,
        "hit_rate": float((daily_ic > 0).mean()) if n else float("nan"),
        "n_days": n,
    }


def signal_decay(signal, forward_returns, lags=(1, 5, 10, 20)):
    """Mean rank IC of a signal at several forward-return lags.

    Shows how fast the edge fades if execution is delayed — a signal
    whose IC collapses by lag 5 is not tradable at realistic speeds.
    """
    return {lag: information_coefficient(signal, forward_returns, lag=lag)["mean_ic"] for lag in lags}


def long_short_backtest(signal, returns, top_quantile=0.2, cost_bps=5.0):
    """Daily long-short quintile backtest of a cross-sectional signal.

    Each day the top ``top_quantile`` of stocks by signal are bought
    and the bottom ``top_quantile`` sold, equal-weighted, with the
    signal at day ``t`` applied to returns at ``t + 1`` (no
    look-ahead). Turnover is charged at ``cost_bps`` per unit of
    one-way turnover. Returns a dict with the daily net-return series,
    gross-return series, turnover series, and summary metrics (CAGR,
    annualised volatility, Sharpe, maximum drawdown, mean turnover).
    """
    positions = pd.DataFrame(0.0, index=signal.index, columns=signal.columns)
    n_long = max(1, int(round(top_quantile * len(signal.columns))))
    for day in signal.index:
        ranked = signal.loc[day].dropna()
        if len(ranked) < 2 * n_long:
            continue
        longs = ranked.nlargest(n_long).index
        shorts = ranked.nsmallest(n_long).index
        positions.loc[day, longs] = 1.0 / n_long
        positions.loc[day, shorts] = -1.0 / n_long
    applied = positions.shift(1).fillna(0.0)
    gross = (applied * returns).sum(axis=1)
    turnover = applied.diff().abs().sum(axis=1).fillna(0.0)
    costs = turnover * (cost_bps / 10_000.0)
    net = gross - costs
    net = net.loc[net.index[1:]] if len(net) > 1 else net
    gross = gross.loc[net.index]
    turnover = turnover.loc[net.index]
    cum = (1.0 + net).cumprod()
    peak = cum.cummax()
    drawdown = (cum - peak) / peak
    n_years = len(net) / TRADING_DAYS
    cagr = float(cum.iloc[-1] ** (1.0 / n_years) - 1.0) if n_years > 0 and len(net) else float("nan")
    vol = float(net.std() * np.sqrt(TRADING_DAYS)) if len(net) > 1 else float("nan")
    sharpe = float((net.mean() / net.std()) * np.sqrt(TRADING_DAYS)) if len(net) > 1 and net.std() > 0 else float("nan")
    return {
        "net_returns": net,
        "gross_returns": gross,
        "turnover": turnover,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else float("nan"),
        "mean_turnover": float(turnover.mean()) if len(turnover) else float("nan"),
    }


def alpha_report(prices, characteristics, cost_bps=5.0):
    """One-call research summary for the equity alpha panel.

    Builds momentum, value and quality signals plus an equal-weighted
    composite, reports each signal's IC (lag 1) and decay, and
    backtests the composite long-short. Returns a dict of the pieces
    so a researcher can read the verdict in one place.
    """
    returns = prices.pct_change().fillna(0.0)
    momentum = cross_sectional_momentum(prices)
    value = value_signal(characteristics)
    quality = quality_signal(characteristics)
    composite = combine_signals([momentum, value, quality])
    ics = {
        "momentum": information_coefficient(momentum, returns),
        "value": information_coefficient(
            pd.DataFrame(
                np.tile(value.values, (len(prices), 1)),
                index=prices.index,
                columns=prices.columns,
            ),
            returns,
        ),
        "quality": information_coefficient(
            pd.DataFrame(
                np.tile(quality.values, (len(prices), 1)),
                index=prices.index,
                columns=prices.columns,
            ),
            returns,
        ),
        "composite": information_coefficient(composite, returns),
    }
    decay = signal_decay(composite, returns)
    backtest = long_short_backtest(composite, returns, cost_bps=cost_bps)
    return {
        "ics": ics,
        "decay": decay,
        "backtest": {k: v for k, v in backtest.items() if not isinstance(v, pd.Series)},
    }
