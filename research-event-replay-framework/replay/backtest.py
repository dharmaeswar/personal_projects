"""Research tooling: slice, backtest, and measure.

Thin Python helpers a researcher uses on replayed data: a momentum signal
over bar closes, a no-lookahead backtest that trades at the next bar, and
the standard performance metrics (total return, Sharpe, max drawdown).
All inputs are synthetic; results describe the seeded demo data only.
"""

from __future__ import annotations

import math

from .replay import to_bars


def momentum_signal(closes: list[float], lookback: int) -> list[int]:
    """+1 when the close is above its trailing mean, -1 when below, else 0."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    signals: list[int] = []
    for i, close in enumerate(closes):
        if i < lookback:
            signals.append(0)
            continue
        window = closes[i - lookback : i]
        mean = sum(window) / len(window)
        signals.append(1 if close > mean else -1 if close < mean else 0)
    return signals


def backtest(closes: list[float], lookback: int) -> dict:
    """Backtest the momentum signal: position set at bar i trades bar i+1.

    Returns per-bar strategy returns plus summary metrics. No look-ahead:
    the signal at bar i only ever trades the return after bar i.
    """
    if len(closes) < lookback + 2:
        raise ValueError("need at least lookback + 2 closes")
    signals = momentum_signal(closes, lookback)
    strat_returns: list[float] = []
    for i in range(len(closes) - 1):
        bar_ret = closes[i + 1] / closes[i] - 1.0
        strat_returns.append(signals[i] * bar_ret)
    total = 1.0
    for r in strat_returns:
        total *= 1.0 + r
    total_return = total - 1.0
    mean = sum(strat_returns) / len(strat_returns)
    var = sum((r - mean) ** 2 for r in strat_returns) / len(strat_returns)
    sharpe = (mean / math.sqrt(var)) if var > 0 else 0.0
    peak = 1.0
    equity = 1.0
    max_dd = 0.0
    for r in strat_returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    return {
        "bars": len(closes),
        "trades": sum(1 for s in signals if s != 0),
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "returns": strat_returns,
    }


def backtest_ticks(ticks: list, bar_ns: int, lookback: int) -> dict:
    """Backtest directly from trade ticks: aggregate to bars, then run."""
    bars = to_bars(ticks, bar_ns)
    closes = [b["close"] for b in bars]
    result = backtest(closes, lookback)
    result["bars"] = len(bars)
    return result
