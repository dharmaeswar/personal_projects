"""Advertising-data ETL + pipeline validation (Amazon DEPO-style).

Bronze -> silver -> gold over synthetic ad event data, using only the
Python standard library (sqlite3 for SQL transforms). No cluster, no
external services: the pipeline runs locally and deterministically.
"""

from .checks import CheckResult  # noqa: F401  (re-exported for convenience)
from .pipeline import build_gold, build_silver, load_bronze

__all__ = ["build_gold", "build_silver", "load_bronze"]
