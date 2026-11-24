"""Compliance model risk validation package.

Independent validation of the models a compliance team relies on: an
AML transaction-monitoring alert model, fair-lending disparate-impact
checks, and the governance of the compliance model inventory.
All data is synthetic and seeded.
"""

from .data import generate_alert_book, generate_monitoring_book
from .alert_model import train_champion, train_challenger, train_benchmark
from .outcomes import outcomes_summary, decile_capture, calibration_by_decile
from .threshold import threshold_table, review_burden
from .monitoring import psi, mean_drift_pct
from .fairness import flag_rates_by_group, disparate_impact_ratio, equal_opportunity_gap
from .governance import ModelInventory, validation_cadence_days

__all__ = [
    "generate_alert_book",
    "generate_monitoring_book",
    "train_champion",
    "train_challenger",
    "train_benchmark",
    "outcomes_summary",
    "decile_capture",
    "calibration_by_decile",
    "threshold_table",
    "review_burden",
    "psi",
    "mean_drift_pct",
    "flag_rates_by_group",
    "disparate_impact_ratio",
    "equal_opportunity_gap",
    "ModelInventory",
    "validation_cadence_days",
]
