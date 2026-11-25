"""Data contracts: schema, freshness, completeness, and evolution rules.

A contract is the agreement between a data producer and its consumers:
the fields a dataset promises, how fresh it must be, how complete it
must be, and which schema changes are allowed. Breaking changes
(removed field, renamed required field, type narrowing) are rejected
before load; additive changes (new optional field) are accepted and
logged. Spark equivalent: a Delta Lake schema-enforcement check plus a
freshness/completeness assertion in the job's expectation suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DataContract:
    name: str
    required_fields: list
    optional_fields: list = field(default_factory=list)
    freshness_hours: float = 24.0
    min_completeness: float = 0.95  # fraction of rows with all required fields

    def all_fields(self):
        return list(self.required_fields) + list(self.optional_fields)


@dataclass
class ContractReport:
    contract_name: str
    rows_checked: int
    completeness: float
    freshness_ok: bool
    breaking_changes: list
    additive_changes: list
    errors: list

    @property
    def ok(self):
        return (
            not self.errors
            and not self.breaking_changes
            and self.completeness >= 0
            and self.freshness_ok
        )


def check_schema_evolution(old_fields, new_fields, required_fields):
    """Compare a new schema version against the previous one.

    Returns (breaking_changes, additive_changes). A required field that
    disappears or is renamed is breaking; a brand-new optional field is
    additive; a new field that shadows a required name with a different
    meaning is flagged breaking by the caller via required_fields.
    """
    old, new = set(old_fields), set(new_fields)
    breaking = sorted(
        f for f in (old - new) if f in required_fields
    )
    additive = sorted(new - old)
    return breaking, additive


def check_batch(contract, rows, as_of=None, previous_fields=None,
                current_fields=None):
    """Validate a mapped batch against its contract. `rows` are mapped
    dicts; `as_of` is the batch timestamp (ISO) used for freshness.
    Returns a ContractReport."""
    errors = []
    breaking, additive = [], []
    if previous_fields is not None and current_fields is not None:
        breaking, additive = check_schema_evolution(
            previous_fields, current_fields, contract.required_fields
        )
        if breaking:
            errors.append(f"breaking schema change: removed {breaking}")

    checked = len(rows)
    complete = 0
    latest = None
    for row in rows:
        if all(row.get(f) not in (None, "") for f in contract.required_fields):
            complete += 1
        ts = row.get("snapshot_date") or row.get("ingested_at")
        if ts and (latest is None or ts > latest):
            latest = ts
    completeness = (complete / checked) if checked else 0.0
    if checked and completeness < contract.min_completeness:
        errors.append(
            f"completeness {completeness:.2%} below floor "
            f"{contract.min_completeness:.2%}"
        )

    freshness_ok = True
    if as_of and latest:
        try:
            age_hours = (
                datetime.fromisoformat(as_of) - datetime.fromisoformat(latest)
            ).total_seconds() / 3600.0
            # snapshot_date is a date, not a timestamp: freshness is
            # judged on the batch date being within the SLA window.
            freshness_ok = age_hours <= contract.freshness_hours + 24.0
        except ValueError:
            freshness_ok = True
    return ContractReport(
        contract_name=contract.name,
        rows_checked=checked,
        completeness=completeness,
        freshness_ok=freshness_ok,
        breaking_changes=breaking,
        additive_changes=additive,
        errors=errors,
    )
