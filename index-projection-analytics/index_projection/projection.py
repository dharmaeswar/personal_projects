"""Forward-looking index projections and benchmark-relative analysis.

Project the index level under per-constituent return scenarios, then
compare the projected index return series with a benchmark: excess
returns, tracking error (population standard deviation of daily excess
returns, annualised by sqrt(252)) and the information ratio.
"""

import math

from .universe import IndexUniverse


def project_level(universe: IndexUniverse, returns: dict) -> float:
    """Projected index level if each constituent returns as given.

    `returns` maps ticker -> simple return (e.g. 0.05 = +5%). Tickers
    absent from the map are assumed flat.
    """
    projected_total = sum(
        c.free_float_mcap * (1.0 + returns.get(t, 0.0))
        for t, c in universe.constituents.items()
    )
    return projected_total / universe.divisor


def excess_returns(index_returns: list, benchmark_returns: list) -> list:
    """Period-by-period index return minus benchmark return."""
    if len(index_returns) != len(benchmark_returns):
        raise ValueError("index and benchmark return series must match in length")
    return [i - b for i, b in zip(index_returns, benchmark_returns)]


def tracking_error(excess: list, annualised: bool = True) -> float:
    """Tracking error: population stdev of excess returns.

    Annualised by sqrt(252) when the inputs are daily excess returns.
    """
    if len(excess) < 2:
        raise ValueError("need at least two excess returns")
    mean = sum(excess) / len(excess)
    variance = sum((x - mean) ** 2 for x in excess) / len(excess)
    te = math.sqrt(variance)
    return te * math.sqrt(252) if annualised else te


def information_ratio(excess: list) -> float:
    """Annualised mean excess return divided by annualised tracking error."""
    mean_daily = sum(excess) / len(excess)
    te = tracking_error(excess, annualised=True)
    if te == 0:
        raise ValueError("tracking error is zero; information ratio undefined")
    return (mean_daily * 252) / te
