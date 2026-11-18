"""Release-readiness gates.

A release is a plain dict describing what is about to ship. Each gate
checks one part of the checklist and returns a pass/fail result with a
reason. The gate runner blocks the release (overall ``passed=False``)
when any required gate fails and lists every blocking reason, so a
developer sees the full picture instead of fixing one failure at a
time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Migration statements that are risky to run while traffic is live.
# This is a simple text heuristic, not a database migration linter.
RISKY_MIGRATION_PATTERNS = (
    "drop table",
    "drop column",
    "truncate table",
    "alter column",
)


@dataclass
class GateResult:
    """Outcome of one readiness gate."""

    name: str
    passed: bool
    reason: str = ""
    detail: str = ""


@dataclass
class GateReport:
    """Outcome of the full readiness checklist for one release."""

    service: str
    version: str
    passed: bool
    results: list[GateResult] = field(default_factory=list)

    @property
    def blocking_reasons(self) -> list[str]:
        """Reasons from every failed gate, in checklist order."""
        return [r.reason for r in self.results if not r.passed]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)


def gate_unit_tests(release: dict) -> GateResult:
    """Unit tests must have passed in CI for this exact commit."""
    ci = release.get("ci", {})
    if not ci.get("unit_tests_passed"):
        return GateResult(
            name="unit_tests",
            passed=False,
            reason="Unit tests did not pass for commit "
            f"{ci.get('commit', 'unknown')}.",
        )
    return GateResult(
        name="unit_tests",
        passed=True,
        reason="",
        detail=f"{ci.get('tests_run', '?')} tests passed "
        f"for commit {ci.get('commit', 'unknown')}.",
    )


def gate_config_review(release: dict) -> GateResult:
    """A config diff must exist and be reviewed by someone other than
    the author before it ships."""
    config = release.get("config", {})
    if not config.get("diff_present"):
        return GateResult(
            name="config_review",
            passed=False,
            reason="No config diff attached to the release.",
        )
    if not config.get("reviewed_by"):
        return GateResult(
            name="config_review",
            passed=False,
            reason="Config diff is present but has no reviewer.",
        )
    if config.get("reviewed_by") == release.get("author"):
        return GateResult(
            name="config_review",
            passed=False,
            reason="Config diff was reviewed by its own author; "
            "a second reviewer is required.",
        )
    return GateResult(
        name="config_review",
        passed=True,
        detail=f"Reviewed by {config['reviewed_by']}.",
    )


def gate_migration_safety(release: dict) -> GateResult:
    """Flag migrations that drop/truncate data or alter a column in
    place. Additive changes (new columns, new indexes) pass.
    Releases with no migration pass automatically."""
    migration = release.get("migration_sql", "")
    if not migration.strip():
        return GateResult(
            name="migration_safety",
            passed=True,
            detail="No database migration in this release.",
        )
    lowered = migration.lower()
    hits = [p for p in RISKY_MIGRATION_PATTERNS if p in lowered]
    if hits:
        return GateResult(
            name="migration_safety",
            passed=False,
            reason="Migration contains risky statement(s): "
            + ", ".join(hits)
            + ". Split into expand-then-contract steps or get a DBA review.",
        )
    return GateResult(
        name="migration_safety",
        passed=True,
        detail="Migration contains only additive/compatible statements.",
    )


def gate_dependency_freshness(release: dict) -> GateResult:
    """Every pinned dependency must be no more than one major version
    behind the latest known version. ``dependencies`` maps a package
    name to ``(pinned_major, latest_major)``."""
    deps = release.get("dependencies", {})
    stale = {
        name: (pinned, latest)
        for name, (pinned, latest) in deps.items()
        if latest - pinned > 1
    }
    if stale:
        detail = ", ".join(
            f"{name} pinned at v{pinned}, latest v{latest}"
            for name, (pinned, latest) in sorted(stale.items())
        )
        return GateResult(
            name="dependency_freshness",
            passed=False,
            reason="Dependencies more than one major version behind: "
            + detail + ".",
        )
    return GateResult(
        name="dependency_freshness",
        passed=True,
        detail=f"{len(deps)} dependencies within one major version of latest.",
    )


def gate_rollback_plan(release: dict) -> GateResult:
    """A rollback plan must name both the previous version to return
    to and how to get there."""
    plan = release.get("rollback_plan", {})
    if not plan.get("previous_version"):
        return GateResult(
            name="rollback_plan",
            passed=False,
            reason="No previous version named in the rollback plan.",
        )
    if not plan.get("steps"):
        return GateResult(
            name="rollback_plan",
            passed=False,
            reason="Rollback plan names a previous version but lists "
            "no steps to get there.",
        )
    return GateResult(
        name="rollback_plan",
        passed=True,
        detail=f"Rolls back to {plan['previous_version']} in "
        f"{len(plan['steps'])} step(s).",
    )


GATES = (
    gate_unit_tests,
    gate_config_review,
    gate_migration_safety,
    gate_dependency_freshness,
    gate_rollback_plan,
)


def run_readiness_gates(release: dict) -> GateReport:
    """Run every gate over ``release`` and return the combined report.

    ``release`` needs ``service`` and ``version`` keys; the gates read
    ``ci``, ``config``, ``migration_sql``, ``dependencies``,
    ``rollback_plan`` and ``author`` as described above.
    """
    results = [gate(release) for gate in GATES]
    return GateReport(
        service=release.get("service", "unknown"),
        version=release.get("version", "unknown"),
        passed=all(r.passed for r in results),
        results=results,
    )
