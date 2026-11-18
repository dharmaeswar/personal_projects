"""Evaluator: score an AI-assisted code migration on behaviour and hygiene.

The evaluator executes the original and migrated sources in separate
namespaces and compares outputs on the sample's fixed cases. It also checks
invariants that a behaviour test alone would miss: the public function names
must survive, the code must parse, and no legacy idiom (``xrange``,
``has_key``, ``%`` formatting, print statements) may remain.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass, field

LEGACY_PATTERNS = ("xrange(", ".has_key(", '" % ', "' % ", "print ")


@dataclass
class CaseResult:
    function: str
    args: tuple
    expected: object
    original: object
    migrated: object
    passed: bool


@dataclass
class EvaluationReport:
    sample: str
    total_cases: int
    passed_cases: int
    behaviour_score: float
    invariants_ok: bool
    invariant_failures: list[str] = field(default_factory=list)
    leftover_legacy: list[str] = field(default_factory=list)
    lines_changed: int = 0
    overall_score: float = 0.0
    case_results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.behaviour_score == 1.0 and self.invariants_ok


def _exec_source(source: str) -> dict:
    """Execute source in an isolated namespace; raise on any error."""
    namespace: dict = {}
    exec(compile(source, "<migration>", "exec"), namespace)  # noqa: S102
    return namespace


def _public_functions(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


def _leftover_legacy(source: str) -> list[str]:
    return [p for p in LEGACY_PATTERNS if p in source]


class MigrationEvaluator:
    """Score one migration of one sample."""

    def __init__(self, legacy_source: str, cases: list[tuple[str, tuple, object]]):
        self.legacy_source = legacy_source
        self.cases = cases

    def evaluate(self, migrated_source: str, sample_name: str = "") -> EvaluationReport:
        failures: list[str] = []
        try:
            original_ns = _exec_source(self.legacy_source)
        except Exception as exc:  # pragma: no cover - invalid fixture
            failures.append(f"legacy source failed to execute: {exc}")
            original_ns = {}
        try:
            migrated_ns = _exec_source(migrated_source)
        except Exception as exc:
            failures.append(f"migrated source failed to execute: {exc}")
            migrated_ns = {}

        # Invariant: same public function names.
        if original_ns and migrated_ns:
            try:
                missing = _public_functions(self.legacy_source) - _public_functions(
                    migrated_source
                )
            except SyntaxError as exc:
                missing = set()
                failures.append(f"migrated source does not parse: {exc}")
            if missing:
                failures.append(f"missing public functions: {sorted(missing)}")

        leftover = _leftover_legacy(migrated_source)
        if leftover:
            failures.append(f"leftover legacy idioms: {leftover}")

        case_results: list[CaseResult] = []
        for fn_name, args, expected in self.cases:
            # The expected value is the contract. The legacy original may not
            # even run under the current interpreter (e.g. Python 2 idioms
            # like xrange), so a failed original call falls back to it.
            orig_fn = original_ns.get(fn_name)
            mig_fn = migrated_ns.get(fn_name)
            try:
                orig_value = orig_fn(*args) if callable(orig_fn) else None
            except Exception:
                orig_value = None
            try:
                mig_value = mig_fn(*args) if callable(mig_fn) else None
            except Exception:
                mig_value = None
            passed = mig_value == expected and (
                orig_value is None or mig_value == orig_value
            )
            case_results.append(
                CaseResult(
                    function=fn_name,
                    args=args,
                    expected=expected,
                    original=orig_value,
                    migrated=mig_value,
                    passed=passed,
                )
            )

        passed_cases = sum(r.passed for r in case_results)
        behaviour = passed_cases / len(case_results) if case_results else 0.0
        lines_changed = len(
            list(
                difflib.unified_diff(
                    self.legacy_source.splitlines(),
                    migrated_source.splitlines(),
                    lineterm="",
                )
            )
        )
        hygiene = 0.0 if failures else 1.0
        overall = round(0.7 * behaviour + 0.3 * hygiene, 4)

        return EvaluationReport(
            sample=sample_name,
            total_cases=len(case_results),
            passed_cases=passed_cases,
            behaviour_score=round(behaviour, 4),
            invariants_ok=not failures,
            invariant_failures=failures,
            leftover_legacy=leftover,
            lines_changed=lines_changed,
            overall_score=overall,
            case_results=case_results,
        )


def evaluate_migration(
    sample_name: str,
    migrated_source: str,
    *,
    legacy_source: str,
    cases: list[tuple[str, tuple, object]],
) -> EvaluationReport:
    """One-call evaluation of a migrated source against a legacy sample."""
    return MigrationEvaluator(legacy_source, cases).evaluate(
        migrated_source, sample_name
    )
