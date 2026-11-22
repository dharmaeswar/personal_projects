"""CCPA / GDPR subject erasure (right to be forgotten).

Given a subject id, find that subject's records across every seeded
dataset and delete them. Datasets under legal hold are skipped and
reported as held — a hold overrides an erasure request. Datasets with
no matching rows are reported as not-found. The result is an audit
report: what was erased, what was held, and what was never there.

Local simulation: rows live in in-memory tables, so "deletion" removes
the matching dicts from the dataset's row list. A production erasure
would issue DELETEs against Snowflake / Postgres and object deletes in
S3, then verify with a re-scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .catalog import Catalog

ERASED = "erased"
HELD = "held"
NOT_FOUND = "not-found"


@dataclass(frozen=True)
class ErasureEntry:
    dataset: str
    outcome: str  # erased | held | not-found
    records_removed: int
    detail: str


@dataclass
class ErasureReport:
    subject_id: str
    entries: List[ErasureEntry] = field(default_factory=list)

    @property
    def erased_total(self) -> int:
        return sum(e.records_removed for e in self.entries if e.outcome == ERASED)

    @property
    def held_datasets(self) -> List[str]:
        return [e.dataset for e in self.entries if e.outcome == HELD]

    def as_dict(self) -> Dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "erased_total": self.erased_total,
            "held_datasets": self.held_datasets,
            "entries": [
                {
                    "dataset": e.dataset,
                    "outcome": e.outcome,
                    "records_removed": e.records_removed,
                    "detail": e.detail,
                }
                for e in self.entries
            ],
        }


def process_erasure(catalog: Catalog, subject_id: str,
                    subject_column: str = "subject_id") -> ErasureReport:
    """Erase ``subject_id`` from every dataset that holds it."""
    report = ErasureReport(subject_id=subject_id)
    for dataset in catalog.all():
        matching = [row for row in dataset.rows if row.get(subject_column) == subject_id]
        if dataset.legal_hold:
            if matching:
                report.entries.append(ErasureEntry(
                    dataset=dataset.name,
                    outcome=HELD,
                    records_removed=0,
                    detail=f"{len(matching)} record(s) kept: dataset under legal hold",
                ))
            else:
                report.entries.append(ErasureEntry(
                    dataset=dataset.name,
                    outcome=NOT_FOUND,
                    records_removed=0,
                    detail="no records for subject; dataset under legal hold",
                ))
            continue
        if not matching:
            report.entries.append(ErasureEntry(
                dataset=dataset.name,
                outcome=NOT_FOUND,
                records_removed=0,
                detail="no records for subject",
            ))
            continue
        dataset.rows = [row for row in dataset.rows if row.get(subject_column) != subject_id]
        report.entries.append(ErasureEntry(
            dataset=dataset.name,
            outcome=ERASED,
            records_removed=len(matching),
            detail=f"deleted {len(matching)} record(s) for subject {subject_id}",
        ))
    return report
