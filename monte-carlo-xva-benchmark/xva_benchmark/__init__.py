"""Monte-Carlo XVA Benchmark Framework.

Simulates GBM paths across asset classes, builds exposure profiles
(EE / EPE / PFE), computes CVA / FVA / KVA, and validates the results
against independent closed-form benchmarks within a tolerance band.
"""

from .config import AssetClass, SimulationConfig, XVAConfig, default_asset_classes
from .runner import run_benchmark_suite

__version__ = "1.0.0"

__all__ = [
    "AssetClass",
    "SimulationConfig",
    "XVAConfig",
    "default_asset_classes",
    "run_benchmark_suite",
    "__version__",
]
