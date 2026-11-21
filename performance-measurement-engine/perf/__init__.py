"""Package for the Performance Measurement Engine."""

from .returns import Flow, Valuation, time_weighted_return, modified_dietz, irr, geometric_excess
from .nav import NavPeriod, roll_forward, reconcile, chain_roll_forward
from .benchmark import benchmark_relative, proxy_fill, excess_series
from .fees import FeeTerms, gross_to_net
from .validation import classify_flow, check_value_neutrality, adversarial_timing_cases
from .composite import (
    asset_weighted_return, equal_weighted_return, composite_dispersion,
    composite_summary,
)

__all__ = [
    "Flow", "Valuation", "time_weighted_return", "modified_dietz", "irr",
    "geometric_excess", "NavPeriod", "roll_forward", "reconcile",
    "chain_roll_forward", "benchmark_relative", "proxy_fill",
    "excess_series", "FeeTerms", "gross_to_net", "classify_flow",
    "check_value_neutrality", "adversarial_timing_cases",
    "asset_weighted_return", "equal_weighted_return",
    "composite_dispersion", "composite_summary",
]
