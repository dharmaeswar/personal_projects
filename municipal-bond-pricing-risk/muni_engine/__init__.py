"""Municipal bond pricing and risk engine.

Pure standard-library Python. Covers the core quantitative work of a
municipal-bond market-making desk: tax-exempt yield-curve construction,
callable-bond pricing (yield-to-call / yield-to-worst), option-adjusted
spread via a calibrated binomial short-rate tree, key-rate durations and
DV01, credit-spread scenarios, and a regression-based relative-value screen.

All market data in the demo is synthetic and seeded in code. No real
issuer, CUSIP, or market data appears anywhere in this project.
"""

from .curve import TaxExemptCurve, bootstrap_curve
from .bonds import MunicipalBond, price, yield_to_maturity, yield_to_call, yield_to_worst
from .oas import option_adjusted_spread, callable_bond_price
from .risk import duration_convexity, dv01, key_rate_durations, spread_scenarios
from .relative_value import RelativeValueScreen
from .public_finance import sector_summary, sector_relative_value, sales_ideas

__all__ = [
    "TaxExemptCurve",
    "bootstrap_curve",
    "MunicipalBond",
    "price",
    "yield_to_maturity",
    "yield_to_call",
    "yield_to_worst",
    "option_adjusted_spread",
    "callable_bond_price",
    "duration_convexity",
    "dv01",
    "key_rate_durations",
    "spread_scenarios",
    "RelativeValueScreen",
    "sector_summary",
    "sector_relative_value",
    "sales_ideas",
]
