"""Systematic futures & FX signal research."""

from .backtest import backtest, portfolio_metrics
from .data import generate_carry, generate_prices
from .equity_factor_risk import (
    estimate_factor_betas,
    factor_risk_decomposition,
    generate_equity_panel,
    governance_checks,
    portfolio_risk_summary,
    tracking_error,
)
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
    "estimate_factor_betas",
    "factor_risk_decomposition",
    "generate_carry",
    "generate_equity_panel",
    "generate_prices",
    "governance_checks",
    "mean_reversion",
    "moving_average_crossover",
    "portfolio_metrics",
    "portfolio_risk_summary",
    "signal_decay",
    "sim_vs_actual_gap",
    "time_series_momentum",
    "tracking_error",
    "walk_forward",
]
