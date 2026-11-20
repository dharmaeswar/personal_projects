"""Evaluation harness: run graders, log observably, summarise.

Pipeline per case:
  1. Redact PII from the prompt and the response.
  2. Grade the redacted response with the configured grader.
  3. Check the graded output for leftover PII (a leak).
  4. Append one JSONL log record per case (observability), plus a
     run summary record, so any run can be replayed from its log.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .graders import DeterministicStubGrader
from .redaction import contains_pii, redact_text


@dataclass
class CaseResult:
    case_id: str
    subject: str
    overall: float
    criterion_scores: dict
    notes: list
    redactions: dict
    pii_leak: bool


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    cases: int
    mean_overall: float
    mean_correctness: float
    safety_failures: int
    pii_leaks: int
    total_redactions: int
    per_subject: dict = field(default_factory=dict)


def run_evaluation(cases, grader=None, known_names=(), log_path=None):
    """Run the full evaluation over a list of cases.

    Returns (results, summary). When log_path is given, writes one
    JSON record per case plus a summary record, in JSONL format.
    """
    grader = grader or DeterministicStubGrader()
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    results = []
    total_redactions = 0
    log_handle = open(log_path, "w", encoding="utf-8") if log_path else None

    try:
        for case in cases:
            redacted_prompt, prompt_red = redact_text(case["prompt"], known_names)
            redacted_response, resp_red = redact_text(case["response"], known_names)
            redactions = {}
            for source in (prompt_red, resp_red):
                for key, count in source.items():
                    redactions[key] = redactions.get(key, 0) + count
            total_redactions += sum(redactions.values())

            result = grader.grade(case["case_id"], redacted_prompt,
                                  redacted_response, case["expected_points"])
            leak = contains_pii(redacted_response) or contains_pii(redacted_prompt)
            case_result = CaseResult(
                case_id=case["case_id"],
                subject=case["subject"],
                overall=result.overall,
                criterion_scores=result.criterion_scores,
                notes=result.notes,
                redactions=redactions,
                pii_leak=leak,
            )
            results.append(case_result)
            if log_handle:
                log_handle.write(json.dumps({
                    "run_id": run_id, "type": "case",
                    "case_id": case_result.case_id,
                    "subject": case_result.subject,
                    "overall": case_result.overall,
                    "criterion_scores": case_result.criterion_scores,
                    "notes": case_result.notes,
                    "redactions": case_result.redactions,
                    "pii_leak": case_result.pii_leak,
                }) + "\n")

        mean_overall = round(
            sum(r.overall for r in results) / len(results), 3) if results else 0.0
        correctness = [r.criterion_scores.get("correctness", 0.0) for r in results]
        mean_correctness = round(
            sum(correctness) / len(correctness), 3) if correctness else 0.0
        safety_failures = sum(
            1 for r in results if r.criterion_scores.get("safety", 1.0) == 0.0)
        pii_leaks = sum(1 for r in results if r.pii_leak)
        per_subject = {}
        for r in results:
            per_subject.setdefault(r.subject, []).append(r.overall)
        per_subject = {k: round(sum(v) / len(v), 3) for k, v in per_subject.items()}

        summary = RunSummary(
            run_id=run_id, started_at=started_at, cases=len(results),
            mean_overall=mean_overall, mean_correctness=mean_correctness,
            safety_failures=safety_failures, pii_leaks=pii_leaks,
            total_redactions=total_redactions, per_subject=per_subject)
        if log_handle:
            log_handle.write(json.dumps(
                {"run_id": run_id, "type": "summary", **asdict(summary)}) + "\n")
        return results, summary
    finally:
        if log_handle:
            log_handle.close()
