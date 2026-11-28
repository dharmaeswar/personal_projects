"""Graders: small, explainable scorers for an evaluation harness.

Each grader returns a ``GradeResult`` with a score in [0, 1] and a short
reason, so a harness can aggregate scores and a human can see why a
sample failed. Graders never raise on bad input — unparseable text scores
0 with a reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .tool_calls import ToolCall


@dataclass(frozen=True)
class GradeResult:
    """One grading: a score in [0, 1] and the reason for it."""

    score: float
    reason: str


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def grade_exact_match(predicted: str, expected: str) -> GradeResult:
    """1.0 when the texts match after whitespace/case normalization, else 0.0."""
    if _normalize(predicted) == _normalize(expected):
        return GradeResult(1.0, "exact match after normalization")
    return GradeResult(0.0, f"expected {expected!r}, got {predicted!r}")


def grade_json_validity(text: str) -> GradeResult:
    """1.0 when the text parses as a JSON object, else 0.0."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return GradeResult(0.0, f"invalid JSON: {exc.msg}")
    if isinstance(parsed, dict):
        return GradeResult(1.0, "valid JSON object")
    return GradeResult(0.0, f"valid JSON but not an object (got {type(parsed).__name__})")


def grade_tool_call(call: ToolCall, expected_name: str, expected_args: dict) -> GradeResult:
    """Score a parsed tool call against the expected name and arguments.

    Half the score is the tool name; the other half is the fraction of
    expected arguments present with equal values.
    """
    if call.name != expected_name:
        return GradeResult(0.0, f"wrong tool: expected {expected_name!r}, got {call.name!r}")
    if not expected_args:
        return GradeResult(1.0, "correct tool, no arguments expected")
    matched = sum(1 for key, value in expected_args.items() if call.arguments.get(key) == value)
    score = 0.5 + 0.5 * (matched / len(expected_args))
    if matched == len(expected_args):
        return GradeResult(1.0, "correct tool and all arguments match")
    missing = sorted(key for key in expected_args if call.arguments.get(key) != expected_args[key])
    return GradeResult(score, f"correct tool; mismatched arguments: {missing}")
