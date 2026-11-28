"""Backtest: daily delta-hedged long straddle on a synthetic price path.

The study a research engineer runs with a quant: buy an at-the-money
straddle, re-hedge its delta every day with the underlying, and close
the position at expiry. Positions use only prices known up to the
current day (no look-ahead). Transaction costs are charged per hedge
trade. Metrics: total P&L, Sharpe ratio, max drawdown, win rate.
"""

import math

from .pricing import call_price, greeks, put_price


def delta_hedged_straddle(prices, expiry_days=30, rate=0.05, vol=0.25,
                          cost_per_trade=0.02, start_day=0):
    """Run one delta-hedged straddle trade over ``prices``.

    Buys the ATM straddle on ``start_day`` (strike = spot that day),
    hedges delta daily, and closes at ``start_day + expiry_days``.
    Returns a dict with the daily P&L series and summary metrics.
    """
    if start_day + expiry_days >= len(prices):
        raise ValueError("price path too short for the requested trade")
    strike = round(prices[start_day])
    t0 = expiry_days / 365.0
    call0 = call_price(prices[start_day], strike, t0, rate, vol)
    put0 = put_price(prices[start_day], strike, t0, rate, vol)
    entry_cost = call0 + put0

    hedge = 0.0  # shares of underlying held; negative = short
    cash = -entry_cost  # paid for the straddle
    pnl_series = []
    for day in range(expiry_days + 1):
        idx = start_day + day
        spot = prices[idx]
        remaining = (expiry_days - day) / 365.0
        if day < expiry_days:
            call_delta = greeks(spot, strike, remaining, rate, vol, "call")["delta"]
            put_delta = greeks(spot, strike, remaining, rate, vol, "put")["delta"]
            target_hedge = -(call_delta + put_delta)
        else:
            target_hedge = 0.0  # close everything at expiry
        trade = target_hedge - hedge
        cash -= trade * spot
        cash -= abs(trade) * cost_per_trade
        hedge = target_hedge
        if day < expiry_days:
            call_value = call_price(spot, strike, remaining, rate, vol)
            put_value = put_price(spot, strike, remaining, rate, vol)
            position_value = call_value + put_value + hedge * spot
        else:
            intrinsic = max(spot - strike, 0.0) + max(strike - spot, 0.0)
            position_value = intrinsic
        pnl_series.append(cash + position_value)
    return {
        "strike": strike,
        "entry_cost": entry_cost,
        "pnl_series": pnl_series,
        "total_pnl": pnl_series[-1],
        "sharpe": sharpe_ratio(daily_returns(pnl_series)),
        "max_drawdown": max_drawdown(pnl_series),
    }


def daily_returns(pnl_series):
    """Day-over-day P&L changes (the trade's daily returns in currency)."""
    return [pnl_series[i + 1] - pnl_series[i]
            for i in range(len(pnl_series) - 1)]


def sharpe_ratio(returns):
    """Annualised Sharpe of a return series (risk-free rate assumed zero)."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return mean / std * math.sqrt(252.0)


def max_drawdown(pnl_series):
    """Largest peak-to-trough fall in the P&L series."""
    peak = pnl_series[0]
    worst = 0.0
    for value in pnl_series:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def run_study(prices, expiry_days=30, rate=0.05, vol=0.25,
              cost_per_trade=0.02, step=30):
    """Run the straddle trade on non-overlapping windows across the path.

    Returns a list of per-trade results. Windows start every ``step``
    days; a window is skipped when the path ends before its expiry.
    """
    results = []
    start = 0
    while start + expiry_days < len(prices):
        results.append(delta_hedged_straddle(
            prices, expiry_days, rate, vol, cost_per_trade, start))
        start += step
    return results


def study_summary(results):
    """Aggregate a run_study list: trades, wins, total P&L, avg Sharpe."""
    if not results:
        return {"trades": 0, "wins": 0, "total_pnl": 0.0, "avg_sharpe": 0.0}
    wins = sum(1 for r in results if r["total_pnl"] > 0)
    return {
        "trades": len(results),
        "wins": wins,
        "win_rate": wins / len(results),
        "total_pnl": sum(r["total_pnl"] for r in results),
        "avg_sharpe": sum(r["sharpe"] for r in results) / len(results),
        "worst_drawdown": min(r["max_drawdown"] for r in results),
    }
