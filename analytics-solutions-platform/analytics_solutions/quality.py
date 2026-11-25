"""Data-quality gates — the CI-style check that guards every publish.

Each check is named, returns a pass/fail with evidence, and the gate
fails the build when any check fails. No dataset ships with a failing
gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class GateResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def check_completeness(rows: list[dict], required: list[str]) -> CheckResult:
    bad = sum(1 for r in rows for c in required if r.get(c) in (None, ""))
    return CheckResult("completeness", bad == 0,
                       f"{bad} missing values in required columns {required}" if bad else "all required values present")


def check_uniqueness(rows: list[dict], key: str) -> CheckResult:
    seen: set = set()
    dupes = 0
    for r in rows:
        k = r.get(key)
        if k in seen:
            dupes += 1
        seen.add(k)
    return CheckResult("uniqueness", dupes == 0,
                       f"{dupes} duplicate values for {key}" if dupes else f"{key} unique across {len(rows)} rows")


def check_ranges(rows: list[dict], field: str, low: float, high: float) -> CheckResult:
    def _in_range(row: dict) -> bool:
        try:
            return low <= float(row.get(field)) <= high
        except (TypeError, ValueError):
            return False  # missing or non-numeric values fail the range check

    bad = [r for r in rows if not _in_range(r)]
    return CheckResult("range", not bad,
                       f"{len(bad)} rows outside [{low}, {high}] for {field}" if bad else f"{field} within [{low}, {high}]")


def check_referential_integrity(facts: list[dict], dim_keys: dict[str, set],
                                fk_map: dict[str, str]) -> CheckResult:
    """``fk_map``: fact field -> dimension name. ``dim_keys``: dim name -> key set."""
    missing: list[str] = []
    for fact in facts:
        for fk_field, dim_name in fk_map.items():
            if fact.get(fk_field) not in dim_keys.get(dim_name, set()):
                missing.append(f"{fk_field}={fact.get(fk_field)}")
                break
    return CheckResult("referential_integrity", not missing,
                       f"{len(missing)} orphan fact rows: {missing[:3]}" if missing else "all foreign keys resolve")


def check_freshness(as_of: date, max_data_date: date, sla_days: int) -> CheckResult:
    age = (as_of - max_data_date).days
    return CheckResult("freshness", age <= sla_days,
                       f"data is {age} days old, SLA is {sla_days} days" if age > sla_days else f"data is {age} days old, within {sla_days}-day SLA")


def run_quality_gate(rows: list[dict], *, required: list[str], unique_key: str,
                     range_checks: list[tuple[str, float, float]],
                     facts: list[dict] | None = None,
                     dim_keys: dict[str, set] | None = None,
                     fk_map: dict[str, str] | None = None,
                     as_of: date | None = None,
                     max_data_date: date | None = None,
                     sla_days: int = 1) -> GateResult:
    """Run the full gate. Fails when any check fails."""
    checks = [
        check_completeness(rows, required),
        check_uniqueness(rows, unique_key),
    ]
    for field, low, high in range_checks:
        checks.append(check_ranges(rows, field, low, high))
    if facts is not None and dim_keys is not None and fk_map is not None:
        checks.append(check_referential_integrity(facts, dim_keys, fk_map))
    if as_of is not None and max_data_date is not None:
        checks.append(check_freshness(as_of, max_data_date, sla_days))
    return GateResult(passed=all(c.passed for c in checks), checks=checks)
