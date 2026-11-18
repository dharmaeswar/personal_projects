"""Agentic Code Migration Evaluator.

Benchmarks AI-assisted code migration: given legacy Python source and a
migrated version (produced by an agent, an LLM, or the deterministic
transforms in this package), it scores the migration on

* behaviour preservation - the migrated code must produce the same outputs
  as the original on a fixed set of test inputs,
* invariant checks - public API names, signatures and return types survive,
* diff quality - the change is minimal and contains no leftover legacy idioms.

The evaluator never trusts a migration on inspection alone: every score is
computed by executing both versions in isolated namespaces.
"""

from .evaluator import EvaluationReport, MigrationEvaluator, evaluate_migration
from .transforms import apply_transforms, migrate_source

__all__ = [
    "EvaluationReport",
    "MigrationEvaluator",
    "apply_transforms",
    "evaluate_migration",
    "migrate_source",
]
__version__ = "1.0.0"
