"""Invariant framework and the built-in invariant packs.

Importing this package registers all built-in invariants (rates, FX, equity)
into the global REGISTRY.
"""

from .framework import REGISTRY, Invariant, Outcome, invariant, run_suite

# Importing the packs registers their invariants.
from . import rates_invariants  # noqa: F401,E402
from . import fx_invariants  # noqa: F401,E402
from . import equity_invariants  # noqa: F401,E402

__all__ = ["REGISTRY", "Invariant", "Outcome", "invariant", "run_suite"]
