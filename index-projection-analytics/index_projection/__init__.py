"""Index Projection Analytics.

Forward-looking index projections for a free-float market-cap-weighted
equity index: index levels from a divisor, corporate-action adjustments
(splits, cash dividends, spin-offs), projected rebalances with turnover,
and benchmark-relative analysis (excess return, tracking error,
information ratio).

All data is synthetic and seeded. Nothing here describes a real index,
real constituents, real corporate actions, or real BlackRock analytics.
"""

from .universe import Constituent, IndexUniverse
from .corporate_actions import apply_split, apply_cash_dividend, apply_spinoff
from .rebalance import project_rebalance, RebalanceProjection
from .projection import (
    project_level,
    excess_returns,
    tracking_error,
    information_ratio,
)

__all__ = [
    "Constituent",
    "IndexUniverse",
    "apply_split",
    "apply_cash_dividend",
    "apply_spinoff",
    "project_rebalance",
    "RebalanceProjection",
    "project_level",
    "excess_returns",
    "tracking_error",
    "information_ratio",
]
