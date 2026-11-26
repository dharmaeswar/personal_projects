"""Commodity derivatives pricing and risk analytics."""

from .curves import (
    calendar_spreads,
    curve_shape,
    curve_summary,
    implied_convenience_yield,
)
from .data import COMMODITIES, generate_futures_curve, generate_spot_paths
from .pricing import (
    black76_call,
    black76_greeks,
    black76_put,
    implied_vol,
    monte_carlo_price,
)
from .energy_risk import (
    earnings_at_risk,
    potential_future_exposure,
    simulate_degree_days,
    weather_degree_day_option,
)
from .risk import (
    book_value,
    historical_var,
    monte_carlo_var,
    scenario_shocks,
)
from .validation import (
    check_greeks_finite_difference,
    check_mc_convergence,
    check_put_call_parity,
)

__all__ = [
    "COMMODITIES",
    "black76_call",
    "black76_greeks",
    "black76_put",
    "book_value",
    "calendar_spreads",
    "check_greeks_finite_difference",
    "check_mc_convergence",
    "check_put_call_parity",
    "curve_shape",
    "curve_summary",
    "earnings_at_risk",
    "generate_futures_curve",
    "generate_spot_paths",
    "historical_var",
    "implied_convenience_yield",
    "implied_vol",
    "monte_carlo_price",
    "monte_carlo_var",
    "potential_future_exposure",
    "scenario_shocks",
    "simulate_degree_days",
    "weather_degree_day_option",
]
