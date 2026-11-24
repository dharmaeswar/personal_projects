"""AI evaluation and verification framework — golden datasets,
scoring, regression gates and grounding checks.

The framework is model-free and deterministic: the "judge" is a
pluggable callable with a simple rubric default (accuracy of the
reported numbers, grounding of every number in source data, and
completeness against the expected fields). A regression gate compares
a run's scores against a stored baseline and fails the run when any
score drops — the shape of the LLM-as-judge + human-review scoring
and regression testing the posting asks for, without a real model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    source_numbers: dict  # field -> true value; the grounding source
    expected_numbers: dict  # field -> expected value in the answer
    expected_fields: list[str] = field(default_factory=list)


def rubric_judge(case: GoldenCase, answer_numbers: dict,
                 answer_text: str) -> dict:
    """Deterministic rubric judge: accuracy (numbers match the
    expected values), grounding (every reported number traces to a
    source value), completeness (every expected field is present)."""
    checks = {}
    correct = sum(1 for k, v in case.expected_numbers.items()
                  if answer_numbers.get(k) == v)
    total = len(case.expected_numbers)
    checks["accuracy"] = correct / total if total else 1.0
    grounded = all(v in case.source_numbers.values()
                   for v in answer_numbers.values())
    checks["grounding"] = 1.0 if grounded else 0.0
    present = sum(1 for f in case.expected_fields
                  if f in answer_text)
    total_fields = len(case.expected_fields)
    checks["completeness"] = (present / total_fields
                              if total_fields else 1.0)
    score = round(sum(checks.values()) / len(checks), 4)
    ungrounded = [k for k, v in answer_numbers.items()
                  if v not in case.source_numbers.values()]
    return {"score": score, "checks": checks,
            "ungrounded_fields": ungrounded,
            "passed": score >= 0.8 and not ungrounded}


class EvaluationFramework:
    """Golden-dataset evaluation with a regression gate."""

    def __init__(self, cases: list[GoldenCase],
                 judge=rubric_judge) -> None:
        self.cases = {c.case_id: c for c in cases}
        self.judge = judge
        self.baseline: dict[str, float] = {}

    def set_baseline(self, scores: dict[str, float]) -> None:
        self.baseline = dict(scores)

    def evaluate(self, answers: dict[str, dict]) -> dict:
        """answers: case_id -> {"numbers": {...}, "text": "..."}.
        Returns per-case scores and the overall pass/fail."""
        per_case = {}
        for case_id, case in self.cases.items():
            answer = answers.get(case_id)
            if answer is None:
                per_case[case_id] = {"score": 0.0, "passed": False,
                                     "reason": "no answer supplied"}
                continue
            result = self.judge(case, answer.get("numbers", {}),
                                answer.get("text", ""))
            per_case[case_id] = result
        passed = sum(1 for r in per_case.values() if r["passed"])
        return {"cases": len(self.cases), "passed": passed,
                "overall_passed": passed == len(self.cases),
                "per_case": per_case}

    def regression_gate(self, current: dict[str, float]) -> dict:
        """Fail when any case scores below its baseline — a
        regression gate. Cases with no baseline are skipped."""
        regressions = {cid: (self.baseline[cid], score)
                       for cid, score in current.items()
                       if cid in self.baseline
                       and score < self.baseline[cid]}
        return {"passed": not regressions,
                "regressions": regressions}
