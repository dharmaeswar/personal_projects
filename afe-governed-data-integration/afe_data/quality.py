"""Data quality, schema drift, and quarantine.

Quality checks run on every transformed row before it is published:
required fields present, numeric fields in range, no duplicate natural keys,
and referential checks against the reference set. Schema drift compares the
schema a source shows today against the schema the contract recorded
yesterday: added columns are logged, removed or renamed columns are drift
events that block the load until a human reviews them. Bad rows go to
quarantine with a reason instead of being dropped silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QualityIssue:
    record_id: str
    reason: str
    row_index: int = -1


@dataclass
class QualityReport:
    passed: list[str] = field(default_factory=list)
    quarantined: list[QualityIssue] = field(default_factory=list)

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantined)


@dataclass
class DriftEvent:
    source: str
    kind: str  # "added", "removed", "renamed?"
    detail: str
    blocking: bool


def check_rows(rows: list[dict], required: list[str], numeric_ranges: dict[str, tuple[float, float]],
               key_field: str, reference_ids: set[str] | None = None) -> QualityReport:
    """Validate transformed rows. Returns passed ids and quarantined rows."""
    report = QualityReport()
    seen_keys: set[str] = set()
    for index, row in enumerate(rows):
        record_id = str(row.get(key_field) or row.get("record_id") or "?")
        problems: list[str] = []
        for col in required:
            if row.get(col) in (None, ""):
                problems.append(f"missing {col}")
        for col, (low, high) in numeric_ranges.items():
            value = row.get(col)
            if value is None or value == "":
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                problems.append(f"{col} not numeric: {value!r}")
                continue
            if not (low <= number <= high):
                problems.append(f"{col}={number} outside [{low}, {high}]")
        key = row.get(key_field)
        if key is not None:
            if key in seen_keys:
                problems.append(f"duplicate {key_field}={key}")
            seen_keys.add(key)
        if reference_ids is not None and row.get("client_id") is not None:
            if row["client_id"] not in reference_ids:
                problems.append(f"unknown client_id={row['client_id']}")
        if problems:
            report.quarantined.append(QualityIssue(record_id, "; ".join(problems), index))
        else:
            report.passed.append(record_id)
    return report


def detect_schema_drift(source: str, previous: list[str], current: list[str]) -> list[DriftEvent]:
    """Compare yesterday's recorded schema with today's. Renames are
    reported as a removed + added pair and flagged for human review."""
    events: list[DriftEvent] = []
    prev, cur = set(previous), set(current)
    for col in sorted(cur - prev):
        events.append(DriftEvent(source, "added", f"new column {col}", blocking=False))
    for col in sorted(prev - cur):
        events.append(
            DriftEvent(source, "removed", f"column {col} no longer present", blocking=True)
        )
    return events
