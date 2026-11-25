"""Package for the Performance Measurement Engine."""

from .returns import Flow, Valuation, time_weighted_return, modified_dietz, irr, geometric_excess
from .nav import NavPeriod, roll_forward, reconcile, chain_roll_forward
from .benchmark import benchmark_relative, proxy_fill, excess_series
from .fees import FeeTerms, gross_to_net
from .validation import classify_flow, check_value_neutrality, adversarial_timing_cases
from .decimal_solver import money, canonical_sum, decimal_npv, solve_irr_decimal
from .pme import ks_pme, direct_alpha, long_nickels_pme, discounted_weights
from .decimal_measures import decimal_modified_dietz, chained_index, unitised_return
from .conformance import (
    ENGINE_VERSION, MEASURE_VERSIONS, run_conformance, pin_run,
    input_hash, data_snapshot_hash, GOLDEN_VECTORS,
)
from .batch import FundData, compute_batch
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
    "money", "canonical_sum", "decimal_npv", "solve_irr_decimal",
    "ks_pme", "direct_alpha", "long_nickels_pme", "discounted_weights",
    "decimal_modified_dietz", "chained_index", "unitised_return",
    "ENGINE_VERSION", "MEASURE_VERSIONS", "GOLDEN_VECTORS",
    "input_hash", "data_snapshot_hash", "pin_run", "run_conformance",
    "FundData", "compute_batch",
]
