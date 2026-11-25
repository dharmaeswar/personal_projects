"""Data contracts: the agreement between a dataset's producer and its
consumers.

A contract names the dataset, its owner, the schema consumers may rely
on, the freshness SLA, and the minimum daily row count. Validation
checks a candidate table against the contract and returns violations
— a violation is a result, not an exception, so a broken contract is
reported instead of crashing the pipeline.

Breaking-change detection compares two schema versions: removing a
column or changing a type breaks downstream readers; adding a nullable
column does not. A contract change that breaks readers must be a
versioned, announced change — never a silent feed update.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass
class ContractViolation:
    rule: str
    detail: str
    severity: str = SEVERITY_ERROR

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.severity.upper()}] {self.rule}: {self.detail}"


@dataclass
class DataContract:
    """A data contract for one curated dataset."""

    dataset: str
    owner: str
    team: str
    schema: dict[str, str]  # column -> expected dtype string
    freshness_sla_minutes: int = 60
    min_rows_per_day: int = 1
    version: int = 1
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "owner": self.owner,
            "team": self.team,
            "schema": dict(self.schema),
            "freshness_sla_minutes": self.freshness_sla_minutes,
            "min_rows_per_day": self.min_rows_per_day,
            "version": self.version,
            "description": self.description,
        }


def validate_contract(
    contract: DataContract,
    df: pd.DataFrame,
    latest_event_time: pd.Timestamp | None,
    now: pd.Timestamp,
    event_time_col: str = "event_time",
) -> list[ContractViolation]:
    """Check a table against its contract; return every violation."""
    violations: list[ContractViolation] = []
    actual_types = {col: str(dtype) for col, dtype in df.dtypes.items()}
    for column, expected in contract.schema.items():
        if column not in actual_types:
            violations.append(
                ContractViolation(
                    rule="schema.missing_column",
                    detail=f"column '{column}' is missing from the table",
                )
            )
        elif actual_types[column] != expected:
            violations.append(
                ContractViolation(
                    rule="schema.type_mismatch",
                    detail=(
                        f"column '{column}' is {actual_types[column]}, "
                        f"contract expects {expected}"
                    ),
                )
            )
    extra = [c for c in actual_types if c not in contract.schema]
    if extra:
        violations.append(
            ContractViolation(
                rule="schema.extra_columns",
                detail=f"uncontracted columns present: {', '.join(extra)}",
                severity=SEVERITY_WARNING,
            )
        )
    if len(df) < contract.min_rows_per_day:
        violations.append(
            ContractViolation(
                rule="volume.min_rows",
                detail=(
                    f"{len(df)} rows, contract requires at least "
                    f"{contract.min_rows_per_day} per day"
                ),
            )
        )
    if latest_event_time is None:
        violations.append(
            ContractViolation(
                rule="freshness.no_events",
                detail="no event time available to check freshness",
            )
        )
    else:
        age_minutes = (now - latest_event_time).total_seconds() / 60
        if age_minutes > contract.freshness_sla_minutes:
            violations.append(
                ContractViolation(
                    rule="freshness.sla_breach",
                    detail=(
                        f"latest event is {age_minutes:.0f} minutes old, "
                        f"SLA is {contract.freshness_sla_minutes} minutes"
                    ),
                )
            )
    return violations


@dataclass
class SchemaChange:
    change: str
    breaking: bool


def detect_breaking_change(
    old_schema: dict[str, str], new_schema: dict[str, str]
) -> list[SchemaChange]:
    """Classify each schema difference as breaking or non-breaking.

    Removed columns and type changes break readers. Adding a column
    is non-breaking only when the new column is nullable (marked by a
    ``?`` suffix on the type, e.g. ``"string?"``); adding a required
    column breaks writers that do not supply it.
    """
    changes: list[SchemaChange] = []
    for column in old_schema:
        if column not in new_schema:
            changes.append(
                SchemaChange(f"removed column '{column}'", breaking=True)
            )
        elif new_schema[column] != old_schema[column]:
            changes.append(
                SchemaChange(
                    f"type of '{column}': {old_schema[column]} -> "
                    f"{new_schema[column]}",
                    breaking=True,
                )
            )
    for column, dtype in new_schema.items():
        if column not in old_schema:
            nullable = dtype.endswith("?")
            changes.append(
                SchemaChange(
                    f"added column '{column}' ({dtype})",
                    breaking=not nullable,
                )
            )
    return changes


def contract_is_compatible(changes: list[SchemaChange]) -> bool:
    """True when a schema change can ship without a version bump."""
    return not any(change.breaking for change in changes)
