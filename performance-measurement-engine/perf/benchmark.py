"""Benchmark-relative returns, including proxy-filled returns.

When no direct benchmark exists for a period or an asset, a proxy
benchmark fills the gap: the proxy's return is used for the missing
periods, flagged as filled, so the fill is always visible in the output
rather than silently blended in.
"""

from .returns import geometric_excess


def benchmark_relative(portfolio_return, benchmark_return, geometric=True):
    """Excess return of a portfolio over its benchmark."""
    if geometric:
        return geometric_excess(portfolio_return, benchmark_return)
    return portfolio_return - benchmark_return


def proxy_fill(returns, benchmark_returns, proxy_returns):
    """Fill missing benchmark returns with a proxy.

    returns / benchmark_returns / proxy_returns are aligned lists of
    per-period returns; benchmark entries may be None (missing). Returns
    a list of (benchmark_return, was_filled) pairs.
    """
    if not (len(returns) == len(benchmark_returns) == len(proxy_returns)):
        raise ValueError("series must be aligned")
    filled = []
    for bench, proxy in zip(benchmark_returns, proxy_returns):
        if bench is None:
            if proxy is None:
                raise ValueError("no benchmark and no proxy for a period")
            filled.append((proxy, True))
        else:
            filled.append((bench, False))
    return filled


def excess_series(portfolio_returns, benchmark_returns, proxy_returns=None,
                  geometric=True):
    """Per-period excess returns with proxy fills. Returns a list of dicts
    with portfolio, benchmark, filled flag, and excess return."""
    if proxy_returns is None:
        proxy_returns = [None] * len(portfolio_returns)
    filled = proxy_fill(portfolio_returns, benchmark_returns, proxy_returns)
    out = []
    for portfolio, (bench, was_filled) in zip(portfolio_returns, filled):
        out.append({
            "portfolio": portfolio,
            "benchmark": bench,
            "filled": was_filled,
            "excess": benchmark_relative(portfolio, bench, geometric=geometric),
        })
    return out
