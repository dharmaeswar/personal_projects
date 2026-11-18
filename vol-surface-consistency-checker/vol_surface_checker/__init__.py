"""Vol-Surface Consistency Checker.

Batch arbitrage and consistency checks for implied-volatility surfaces:
calendar and butterfly arbitrage, strike monotonicity, stale-quote
detection and per-expiry RMS smile error, with fast alerts on failure.
"""

from .alerts import AlertSink
from .black_scholes import bs_price, implied_vol, total_variance
from .checks import CheckReport, Violation, run_all_checks
from .surface import Quote, Surface, load_surface

__all__ = [
    "AlertSink",
    "CheckReport",
    "Quote",
    "Surface",
    "Violation",
    "bs_price",
    "implied_vol",
    "load_surface",
    "run_all_checks",
    "total_variance",
]

__version__ = "1.0.0"
