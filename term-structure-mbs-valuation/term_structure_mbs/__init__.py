"""Term-structure modeling and Agency MBS valuation toolkit."""

from .curves import NelsonSiegelCurve, ZeroCurve, fit_nelson_siegel, flat_curve
from .hull_white import HullWhiteModel
from .prepayment import cpr_to_smm, smm_to_cpr, psa_cpr, incentive_multiplier, monthly_cpr
from .mbs import Pool, project_cashflows, static_price, mc_price, solve_oas
from .analytics import effective_duration_convexity, scenario_prices

__all__ = [
    "NelsonSiegelCurve",
    "ZeroCurve",
    "fit_nelson_siegel",
    "flat_curve",
    "HullWhiteModel",
    "cpr_to_smm",
    "smm_to_cpr",
    "psa_cpr",
    "incentive_multiplier",
    "monthly_cpr",
    "Pool",
    "project_cashflows",
    "static_price",
    "mc_price",
    "solve_oas",
    "effective_duration_convexity",
    "scenario_prices",
]
