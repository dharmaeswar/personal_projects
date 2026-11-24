"""Render a review as Markdown or JSON for a human reviewer or a bot."""

from __future__ import annotations

import json

from .review import Review


def to_markdown(review: Review) -> str:
    signals = review.signals
    lines = [f"# Change Review — {review.verdict}", ""]
    lines.append(f"**Risk score:** {review.risk_score}/100")
    if signals is not None:
        lines.append(
            f"**Change size:** {signals.files_changed} files, "
            f"+{signals.lines_added} / -{signals.lines_removed} lines"
        )
        if signals.coverage_ratio is not None:
            lines.append(f"**Test coverage of added lines:** {signals.coverage_ratio:.0%}")
    lines.append("")
    lines.append("## Reasons")
    if review.reasons:
        lines.extend(f"- {reason}" for reason in review.reasons)
    else:
        lines.append("- No blocking or warning signals. Safe to approve on signals alone.")
    lines.append("")
    if review.suggested_reviewers:
        lines.append("## Suggested reviewers")
        lines.extend(f"- {name}" for name in review.suggested_reviewers)
        lines.append("")
    if signals is not None and signals.findings:
        lines.append("## Findings")
        lines.extend(f"- {finding}" for finding in signals.findings)
        lines.append("")
    return "\n".join(lines)


def to_json(review: Review) -> str:
    signals = review.signals
    payload = {
        "verdict": review.verdict,
        "risk_score": review.risk_score,
        "reasons": review.reasons,
        "suggested_reviewers": review.suggested_reviewers,
    }
    if signals is not None:
        payload["change"] = {
            "files_changed": signals.files_changed,
            "lines_added": signals.lines_added,
            "lines_removed": signals.lines_removed,
            "coverage_ratio": signals.coverage_ratio,
            "uncovered_added_lines": signals.uncovered_added_lines,
            "source_files_without_tests": signals.source_files_without_tests,
        }
        payload["findings"] = [
            {
                "severity": f.severity,
                "category": f.category,
                "path": f.path,
                "line_no": f.line_no,
                "text": f.text,
            }
            for f in signals.findings
        ]
    return json.dumps(payload, indent=2)
