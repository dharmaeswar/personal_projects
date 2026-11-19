"""Engineering simulation evaluator: benchmark AI-proposed engineering designs.

Modules: beam (cantilever deflection/stress), thermal (1D conduction),
calibration (recover Young's modulus from noisy synthetic measurements),
benchmark (score and rank candidate designs), metrics (MAE/RMSE/tolerance).
"""

from .beam import Beam
from .benchmark import Requirements
from .metrics import mae, max_abs_error, rmse, within_tolerance

__all__ = [
    "Beam",
    "Requirements",
    "mae",
    "max_abs_error",
    "rmse",
    "within_tolerance",
]
