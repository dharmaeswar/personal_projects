"""Systematic trading signals for futures and FX.

Each signal returns a position series in [-1, 1] for one instrument:
+1 is fully long, -1 is fully short. Signals are computed only from
information available at the close of day ``t`` and are applied from
day ``t + 1`` by the backtester, so there is no look-ahead.
"""

import numpy as np
import pandas as pd


def time_series_momentum(prices, lookback=252):
    """Sign of the trailing ``lookback``-day return (trend following).

    The classic time-series momentum signal: long when the instrument
    rose over the lookback window, short when it fell. Position is
    scaled by the strength of the move relative to its own history so
    weak trends take smaller positions.
    """
    ret = prices / prices.shift(lookback) - 1.0
    scale = ret.rolling(lookback, min_periods=20).std()
    scaled = ret / scale.replace(0, np.nan)
    return scaled.clip(-1, 1).fillna(0.0)


def moving_average_crossover(prices, fast=50, slow=200):
    """Fast average above slow average -> long, otherwise short."""
    fast_ma = prices.rolling(fast, min_periods=fast).mean()
    slow_ma = prices.rolling(slow, min_periods=slow).mean()
    pos = pd.Series(np.where(fast_ma > slow_ma, 1.0, -1.0), index=prices.index)
    pos[slow_ma.isna()] = 0.0
    return pos


def carry_signal(carry, cap=1.0):
    """FX carry: long the higher-yielding currency of the pair.

    ``carry`` is the annualised rate differential in percent. The
    position is proportional to the differential and capped, so a
    2% differential is a full position and smaller gaps scale down.
    """
    return (carry / 2.0).clip(-cap, cap)


def mean_reversion(prices, window=20):
    """Short-term mean reversion: fade moves away from the moving average.

    Position is the negative z-score of price versus its trailing
    ``window``-day mean, clipped to [-1, 1]. A price one standard
    deviation above its mean is a -1 (short) position.
    """
    mean = prices.rolling(window, min_periods=window).mean()
    std = prices.rolling(window, min_periods=window).std()
    z = (prices - mean) / std.replace(0, np.nan)
    return (-z).clip(-1, 1).fillna(0.0)


def combine_signals(signals, weights=None):
    """Weighted average of aligned signal series, clipped to [-1, 1].

    ``signals`` is a dict of name -> position Series. ``weights`` is an
    optional dict of name -> weight; equal weights are used when it is
    omitted. Weights are normalised to sum to one.
    """
    names = list(signals)
    if weights is None:
        weights = {n: 1.0 / len(names) for n in names}
    total = sum(weights[n] for n in names)
    combined = sum(signals[n] * (weights[n] / total) for n in names)
    return combined.clip(-1, 1)
