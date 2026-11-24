"""Turn change signals into a review verdict and a reviewer suggestion.

Verdict rules, in order:
- BLOCK: any blocking finding (secret, eval/exec, os.system).
- NEEDS_REVIEW: large change, low test coverage, warning findings, or a
  source file changed with no test file alongside it.
- APPROVE: none of the above.

The risk score (0-100) is a transparent weighted sum, not a model: every
point comes from a named signal, so a reviewer can see why the number is
what it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .signals import LOW_COVERAGE_THRESHOLD, ChangeSignals

VERDICTS = ("APPROVE", "NEEDS_REVIEW", "BLOCK")


@dataclass
class Review:
    verdict: str
    risk_score: int
    reasons: list[str] = field(default_factory=list)
    suggested_reviewers: list[str] = field(default_factory=list)
    signals: ChangeSignals | None = None


def risk_score(signals: ChangeSignals) -> int:
    """0-100 score: each term is named in the review reasons."""
    score = 0
    score += 40 * len(signals.blocking_findings)
    score += 10 * len(signals.warning_findings)
    if signals.is_large:
        score += 15
    ratio = signals.coverage_ratio
    if ratio is not None and ratio < LOW_COVERAGE_THRESHOLD:
        score += 15
    if signals.source_files_without_tests:
        score += 10
    return min(score, 100)


def suggest_reviewers(
    changed_paths: list[str],
    owners: dict[str, list[str]] | None,
) -> list[str]:
    """Longest-prefix ownership match, in owner-file order, deduplicated."""
    if not owners:
        return []
    suggested: list[str] = []
    for path in changed_paths:
        best_prefix = ""
        best_team: list[str] = []
        for prefix, team in owners.items():
            if path.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
                best_team = team
        for person in best_team:
            if person not in suggested:
                suggested.append(person)
    return suggested


def review_change(
    signals: ChangeSignals,
    changed_paths: list[str] | None = None,
    owners: dict[str, list[str]] | None = None,
) -> Review:
    """Aggregate signals into a verdict, a score, reasons, and reviewers."""
    reasons: list[str] = []
    if signals.blocking_findings:
        for finding in signals.blocking_findings:
            reasons.append(f"Blocking: {finding.category} at {finding.path}:{finding.line_no}")
        verdict = "BLOCK"
    else:
        verdict = "APPROVE"
        if signals.is_large:
            reasons.append(
                f"Large change: {signals.lines_added} lines added across "
                f"{signals.files_changed} files"
            )
            verdict = "NEEDS_REVIEW"
        ratio = signals.coverage_ratio
        if ratio is not None and ratio < LOW_COVERAGE_THRESHOLD:
            reasons.append(f"Low test coverage on added lines: {ratio:.0%} covered")
            verdict = "NEEDS_REVIEW"
        if signals.source_files_without_tests:
            reasons.append(
                "Source files changed with no test file in the change: "
                + ", ".join(signals.source_files_without_tests)
            )
            verdict = "NEEDS_REVIEW"
        if signals.warning_findings:
            for finding in signals.warning_findings:
                reasons.append(f"Check: {finding.category} at {finding.path}:{finding.line_no}")
            verdict = "NEEDS_REVIEW"
    return Review(
        verdict=verdict,
        risk_score=risk_score(signals),
        reasons=reasons,
        suggested_reviewers=suggest_reviewers(changed_paths or [], owners),
        signals=signals,
    )
