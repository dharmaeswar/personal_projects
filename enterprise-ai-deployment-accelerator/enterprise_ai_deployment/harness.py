"""Evaluation harness: run cases, score them, log everything.

Each run writes a JSONL observability log (one record per case plus a
summary record) with run id, per-criterion scores and tool traces, so
runs can be replayed and compared — the production signal a deployment
team actually watches.
"""

import json
import statistics
import time
import uuid
from dataclasses import dataclass, field

from .graders import grade_answer


@dataclass
class EvalCase:
    """One representative evaluation case with its expected facts."""

    case_id: str
    question: str
    expected_keywords: list


@dataclass
class EvalResult:
    case_id: str
    question: str
    answer_text: str
    citations: list
    grade: object
    tools_used: list


@dataclass
class EvalSummary:
    run_id: str
    total: int
    passed: int
    pass_rate: float
    mean_correctness: float
    mean_grounding: float
    p95_latency_ms: float
    total_cost_usd: float
    pii_leaks: int


def _p95(values: list) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return round(ordered[idx], 2)


def run_eval(agent, cases: list, log_path: str = None,
             min_correctness: float = 0.5) -> tuple:
    """Run every case through the agent, grade it, return (results, summary).
    Writes a JSONL log when ``log_path`` is given."""
    run_id = uuid.uuid4().hex[:8]
    results = []
    for case in cases:
        start = time.monotonic()
        answer = agent.run(case.question)
        latency_ms = (time.monotonic() - start) * 1000
        grade = grade_answer(answer, case.expected_keywords, latency_ms,
                             min_correctness=min_correctness)
        results.append(EvalResult(case.case_id, case.question, answer.text,
                                  answer.citations, grade, answer.tools_used))
    passed = sum(1 for r in results if r.grade.passed)
    total = len(results)
    leaks = sum(1 for r in results if r.grade.safety == 0.0)
    summary = EvalSummary(
        run_id=run_id,
        total=total,
        passed=passed,
        pass_rate=round(passed / total, 2) if total else 0.0,
        mean_correctness=round(
            statistics.mean([r.grade.correctness for r in results]), 2)
        if results else 0.0,
        mean_grounding=round(
            statistics.mean([r.grade.grounding for r in results]), 2)
        if results else 0.0,
        p95_latency_ms=_p95([r.grade.latency_ms for r in results]),
        total_cost_usd=round(sum(r.grade.cost_usd for r in results), 6),
        pii_leaks=leaks,
    )
    if log_path:
        with open(log_path, "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps({
                    "run_id": run_id, "case_id": r.case_id,
                    "question": r.question, "answer": r.answer_text,
                    "citations": r.citations,
                    "correctness": r.grade.correctness,
                    "grounding": r.grade.grounding,
                    "safety": r.grade.safety,
                    "latency_ms": r.grade.latency_ms,
                    "cost_usd": r.grade.cost_usd,
                    "passed": r.grade.passed,
                    "notes": r.grade.notes,
                    "tools_used": r.tools_used,
                }) + "\n")
            fh.write(json.dumps({"run_id": run_id, "summary": {
                "total": summary.total, "passed": summary.passed,
                "pass_rate": summary.pass_rate,
                "mean_correctness": summary.mean_correctness,
                "mean_grounding": summary.mean_grounding,
                "p95_latency_ms": summary.p95_latency_ms,
                "total_cost_usd": summary.total_cost_usd,
                "pii_leaks": summary.pii_leaks,
            }}) + "\n")
    return results, summary
