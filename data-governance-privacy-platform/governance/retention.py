"""Retention enforcement: deletion candidates vs. legal holds.

A dataset whose age (days since its oldest record) exceeds its
``retention_days`` is a deletion candidate — unless it is under legal
hold, in which case deletion is blocked entirely and the dataset is
reported as ``held``. Nothing here deletes data itself; it produces the
per-dataset action list that a retention job (Snowflake / S3 lifecycle /
Postgres purge) would execute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .catalog import Catalog, Dataset

RETAIN = "retain"
DELETE_CANDIDATE = "delete-candidate"
HELD = "held"


@dataclass(frozen=True)
class RetentionAction:
    dataset: str
    age_days: int
    retention_days: int
    legal_hold: bool
    action: str  # retain | delete-candidate | held
    reason: str


def evaluate_dataset(dataset: Dataset, age_days: int) -> RetentionAction:
    """Decide the retention action for one dataset at a given age."""
    if dataset.legal_hold:
        return RetentionAction(
            dataset=dataset.name,
            age_days=age_days,
            retention_days=dataset.retention_days,
            legal_hold=True,
            action=HELD,
            reason=f"legal hold blocks deletion (age {age_days}d, retention {dataset.retention_days}d)",
        )
    if age_days > dataset.retention_days:
        return RetentionAction(
            dataset=dataset.name,
            age_days=age_days,
            retention_days=dataset.retention_days,
            legal_hold=False,
            action=DELETE_CANDIDATE,
            reason=f"age {age_days}d exceeds retention {dataset.retention_days}d",
        )
    return RetentionAction(
        dataset=dataset.name,
        age_days=age_days,
        retention_days=dataset.retention_days,
        legal_hold=False,
        action=RETAIN,
        reason=f"age {age_days}d within retention {dataset.retention_days}d",
    )


def evaluate_catalog(catalog: Catalog, ages_days: Dict[str, int]) -> List[RetentionAction]:
    """Evaluate every dataset in the catalog, in catalog order."""
    return [evaluate_dataset(ds, ages_days.get(ds.name, 0)) for ds in catalog.all()]
