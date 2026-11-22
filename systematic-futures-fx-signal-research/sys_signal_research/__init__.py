"""Systematic futures & FX signal research."""

from .backtest import backtest, portfolio_metrics
from .data import generate_carry, generate_prices
from .portfolio import build_portfolio
from .robustness import cost_sensitivity, signal_decay, sim_vs_actual_gap, walk_forward
from .signals import (
    carry_signal,
    combine_signals,
    mean_reversion,
    moving_average_crossover,
    time_series_momentum,
)

__all__ = [
    "backtest",
    "build_portfolio",
    "carry_signal",
    "combine_signals",
    "cost_sensitivity",
    "generate_carry",
    "generate_prices",
    "mean_reversion",
    "moving_average_crossover",
    "portfolio_metrics",
    "signal_decay",
    "sim_vs_actual_gap",
    "time_series_momentum",
    "walk_forward",
]
