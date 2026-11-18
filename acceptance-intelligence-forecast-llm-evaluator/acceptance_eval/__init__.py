"""Acceptance-intelligence forecast + LLM evaluation.

Synthetic daily payment-acceptance-rate series, walk-forward forecast
backtesting, and an evaluation harness for LLM-generated analyst notes
(grounding, completeness, and paired baseline-vs-tuned comparison).
All data is synthetic and seeded. Nothing here is a claim about any
real company, merchant, or payment network.
"""

from .series import generate_series, to_values
from .forecast import seasonal_naive, holt, trend_seasonal_forecast, mae, rmse, mape
from .backtest import walk_forward
from .llm_eval import score_grounding, score_completeness, paired_comparison, bonferroni

__all__ = [
    "generate_series",
    "to_values",
    "seasonal_naive",
    "holt",
    "trend_seasonal_forecast",
    "mae",
    "rmse",
    "mape",
    "walk_forward",
    "score_grounding",
    "score_completeness",
    "paired_comparison",
    "bonferroni",
]
