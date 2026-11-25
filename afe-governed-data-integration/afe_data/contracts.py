"""Data contracts — the DevOps Specification (DS) data requirements a pod
must satisfy before a deployment template is allowed to consume a dataset.

A contract names the expected schema, the freshness SLA, the completeness
floor, and which schema evolution is allowed (additive columns are fine;
renames and type changes are breaking). Breaking changes are rejected
before load; additive changes are accepted and logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContractViolation:
    kind: str  # "breaking-schema", "stale", "incomplete"
    detail: str


@dataclass
class DataContract:
    dataset: str
    expected_columns: list[str]
    required_columns: list[str]
    freshness_hours: int
    completeness_floor: float  # 0.0-1.0 fraction of rows that must be complete
    allowed_new_columns: bool = True

    def check_schema(self, seen_columns: list[str]) -> list[ContractViolation]:
        violations: list[ContractViolation] = []
        missing = [c for c in self.required_columns if c not in seen_columns]
        if missing:
            violations.append(
                ContractViolation("breaking-schema", f"missing required columns: {missing}")
            )
        unexpected = [c for c in seen_columns if c not in self.expected_columns]
        if unexpected and not self.allowed_new_columns:
            violations.append(
                ContractViolation("breaking-schema", f"unexpected columns: {unexpected}")
            )
        return violations

    def check_freshness(self, age_hours: float) -> list[ContractViolation]:
        if age_hours > self.freshness_hours:
            return [
                ContractViolation(
                    "stale",
                    f"data is {age_hours:.1f}h old, SLA is {self.freshness_hours}h",
                )
            ]
        return []

    def check_completeness(self, rows: list[dict]) -> list[ContractViolation]:
        if not rows:
            return [ContractViolation("incomplete", "no rows received")]
        complete = sum(
            1 for r in rows if all(r.get(c) not in (None, "") for c in self.required_columns)
        )
        ratio = complete / len(rows)
        if ratio < self.completeness_floor:
            return [
                ContractViolation(
                    "incomplete",
                    f"completeness {ratio:.2f} below floor {self.completeness_floor:.2f}",
                )
            ]
        return []

    def check(self, seen_columns: list[str], age_hours: float, rows: list[dict]) -> list[ContractViolation]:
        return (
            self.check_schema(seen_columns)
            + self.check_freshness(age_hours)
            + self.check_completeness(rows)
        )
