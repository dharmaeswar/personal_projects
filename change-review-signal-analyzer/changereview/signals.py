"""Signal detectors for a parsed change.

Each detector looks at added lines only: what the change introduces is
what the reviewer has to judge. Findings carry a severity so the review
step can turn them into a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diffparse import ChangedFile

# A finding that always blocks: secrets and code-execution patterns.
_BLOCKING_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]{4,}"), "hardcoded credential"),
    (re.compile(r"(?i)aws_(secret_)?access_key_id\s*="), "hardcoded AWS credential"),
    (re.compile(r"\beval\s*\("), "eval() call"),
    (re.compile(r"\bexec\s*\("), "exec() call"),
    (re.compile(r"os\.system\s*\("), "os.system() call"),
]

# A finding that needs a human look, not an automatic block.
_WARNING_PATTERNS = [
    (re.compile(r"(?i)\bTODO\b|\bFIXME\b|\bHACK\b"), "TODO / FIXME / HACK marker"),
    (re.compile(r"^\s*except\s*:"), "bare except clause"),
    (re.compile(r"(?i)select\s+.*\+\s*\w+|f['\"]select\s"), "string-built SQL query"),
    (re.compile(r"print\s*\("), "debug print statement"),
    (re.compile(r"(?i)password\s*=\s*['\"]change ?me['\"]"), "placeholder password"),
]

LARGE_CHANGE_ADDED_LINES = 400
LARGE_CHANGE_FILES = 10
LOW_COVERAGE_THRESHOLD = 0.5


@dataclass
class Finding:
    """One review signal found in an added line."""

    severity: str  # "block", "warn", or "info"
    category: str
    path: str
    line_no: int
    text: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}:{self.line_no} {self.category}: {self.text}"


@dataclass
class ChangeSignals:
    """Everything the review step needs about one change."""

    files_changed: int
    lines_added: int
    lines_removed: int
    findings: list[Finding] = field(default_factory=list)
    uncovered_added_lines: dict[str, list[int]] = field(default_factory=dict)
    source_files_without_tests: list[str] = field(default_factory=list)
    coverage_known: bool = False

    @property
    def blocking_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def warning_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def is_large(self) -> bool:
        return (
            self.lines_added >= LARGE_CHANGE_ADDED_LINES
            or self.files_changed >= LARGE_CHANGE_FILES
        )

    @property
    def coverage_ratio(self) -> float | None:
        """Share of added lines covered by tests, or None if unknown."""
        if not self.coverage_known or self.lines_added == 0:
            return None
        total_uncovered = sum(len(v) for v in self.uncovered_added_lines.values())
        return (self.lines_added - total_uncovered) / self.lines_added


def _scan_patterns(files: list[ChangedFile]) -> list[Finding]:
    findings: list[Finding] = []
    for changed in files:
        for line_no, text in changed.added_lines:
            for pattern, category in _BLOCKING_PATTERNS:
                if pattern.search(text):
                    findings.append(Finding("block", category, changed.path, line_no, text.strip()))
            for pattern, category in _WARNING_PATTERNS:
                if pattern.search(text):
                    findings.append(Finding("warn", category, changed.path, line_no, text.strip()))
    return findings


def _coverage_gaps(
    files: list[ChangedFile],
    coverage: dict[str, set[int]] | None,
) -> dict[str, list[int]]:
    """Added lines with no test coverage, per file. Empty without a map."""
    gaps: dict[str, list[int]] = {}
    if coverage is None:
        return gaps
    for changed in files:
        covered = coverage.get(changed.path, set())
        missing = [no for no, _ in changed.added_lines if no not in covered]
        if missing:
            gaps[changed.path] = missing
    return gaps


def _files_without_tests(files: list[ChangedFile]) -> list[str]:
    """Source files changed with no test file changed alongside them."""
    test_touched = any(f.is_test_file for f in files)
    if test_touched:
        return []
    return [f.path for f in files if not f.is_test_file and f.added_count > 0]


def analyze_change(
    files: list[ChangedFile],
    coverage: dict[str, set[int]] | None = None,
) -> ChangeSignals:
    """Run every detector over a parsed diff and return the signals."""
    findings = _scan_patterns(files)
    signals = ChangeSignals(
        files_changed=len(files),
        lines_added=sum(f.added_count for f in files),
        lines_removed=sum(f.removed_count for f in files),
        findings=findings,
        uncovered_added_lines=_coverage_gaps(files, coverage),
        source_files_without_tests=_files_without_tests(files),
        coverage_known=coverage is not None,
    )
    if signals.is_large:
        signals.findings.append(
            Finding(
                "info",
                "large change",
                "",
                0,
                f"{signals.lines_added} lines added across {signals.files_changed} files",
            )
        )
    return signals
