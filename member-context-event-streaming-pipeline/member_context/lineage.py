"""Lineage and SLOs.

Lineage records every layer's inputs, transform, run id, row counts, and
a SHA-256 fingerprint of its content, so a downstream team can trace any
context row back to the topic and contract version that produced it.
SLOs state the freshness and completeness objectives the pipeline is
measured against, and each run reports whether they were met.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class LineageEntry:
    run_id: str
    layer: str
    source_topic: str
    contract_version: str
    input_rows: int
    output_rows: int
    fingerprint: str
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "layer": self.layer,
            "source_topic": self.source_topic,
            "contract_version": self.contract_version,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "fingerprint": self.fingerprint,
            "recorded_at": self.recorded_at,
        }


def fingerprint(rows: list[dict]) -> str:
    """SHA-256 over the canonical JSON of the rows (order-independent)."""
    canonical = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class SloReport:
    run_id: str
    freshness_p95_minutes: float
    freshness_objective_minutes: float = 15.0
    completeness_ratio: float = 0.0
    completeness_objective: float = 0.95
    quarantined_rows: int = 0

    @property
    def freshness_met(self) -> bool:
        return self.freshness_p95_minutes <= self.freshness_objective_minutes

    @property
    def completeness_met(self) -> bool:
        return self.completeness_ratio >= self.completeness_objective

    @property
    def all_met(self) -> bool:
        return self.freshness_met and self.completeness_met

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "freshness_p95_minutes": round(self.freshness_p95_minutes, 2),
            "freshness_objective_minutes": self.freshness_objective_minutes,
            "freshness_met": self.freshness_met,
            "completeness_ratio": round(self.completeness_ratio, 4),
            "completeness_objective": self.completeness_objective,
            "completeness_met": self.completeness_met,
            "quarantined_rows": self.quarantined_rows,
            "all_met": self.all_met,
        }


def evaluate_slo(
    run_id: str,
    valid_rows: int,
    quarantined_rows: int,
    freshness_p95_minutes: float,
) -> SloReport:
    """Evaluate the run's SLOs.

    Freshness is the p95 ingest lag (percentile, not max: a few late
    arrivals must not fail the whole run). Completeness is the share of
    seen rows that passed contracts; the 0.95 objective is set against
    the seeded data's known ~3% contract-breaking share, so a run fails
    only if the bad-row rate genuinely rises.
    """
    total = valid_rows + quarantined_rows
    completeness = valid_rows / total if total else 1.0
    return SloReport(
        run_id=run_id,
        freshness_p95_minutes=freshness_p95_minutes,
        completeness_ratio=completeness,
        quarantined_rows=quarantined_rows,
    )
