"""Robotaxi performance telemetry package."""
from .data import generate_trips, to_rows, INTERVENTION_TYPES, RELEASES
from .metrics import kpi_summary, kpi_by_release, kpi_by_road
from .stats import poisson_rate_ci_per_1k, compare_rates

__all__ = [
    "generate_trips",
    "to_rows",
    "INTERVENTION_TYPES",
    "RELEASES",
    "kpi_summary",
    "kpi_by_release",
    "kpi_by_road",
    "poisson_rate_ci_per_1k",
    "compare_rates",
]
