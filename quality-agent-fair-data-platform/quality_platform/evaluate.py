"""Evaluation and monitoring for the agentic Quality workflow.

Two layers: a rubric judge scores each agent trajectory (grounding, tool
use, numeric accuracy, coherence) with hard fails for hallucinated
numbers and invalid tool calls; a monitor tracks pass rate and latency
across runs and raises an alert when the system drifts.
"""

from quality_platform.agents import NUMBER_RE, run_investigation
import re

# Seeded eval cases: question + facts the answer must contain.
EVAL_CASES = [
    {"question": "Why did batch release cycle time rise from Q2 to Q3?",
     "must_contain": ["20.0", "27.5", "7.5"]},
    {"question": "What drove the Q3 deviation increase?",
     "must_contain": ["documentation", "7"]},
    {"question": "How many batches were released in Q2 and Q3?",
     "must_contain": ["6"]},
    {"question": "Did the batch-release data pass its quality checks?",
     "must_contain": ["passed"]},
    {"question": "Which quarter had the slower releases?",
     "must_contain": ["27.5"]},
    {"question": "What is the top deviation category overall?",
     "must_contain": ["documentation"]},
]


def judge_trajectory(trajectory):
    """Score one trajectory on four rubric dimensions (0.0-1.0 each).

    Hard fails: any unverified number, or any tool call that errored.
    """
    scores = {"grounding": 1.0, "tool_use": 1.0,
              "numeric_accuracy": 1.0, "coherence": 1.0}
    reasons = []
    calls = trajectory["tool_calls"]
    if any(c["status"] == "error" for c in calls):
        scores["tool_use"] = 0.0
        reasons.append("a tool call errored")
    if not trajectory["validation"]["passed"]:
        scores["numeric_accuracy"] = 0.0
        scores["grounding"] = 0.0
        reasons.append(
            "unverified numbers: "
            + ", ".join(trajectory["validation"]["unverified_numbers"]))
    if not trajectory["evidence"]:
        scores["grounding"] = 0.0
        reasons.append("answer has no grounded evidence")
    if "cannot answer" in trajectory["answer"].lower():
        scores["coherence"] = 0.5
        reasons.append("agent declined to answer")
    mean_score = sum(scores.values()) / len(scores)
    return {"scores": scores, "mean": round(mean_score, 3),
            "passed": mean_score >= 0.75 and not reasons,
            "reasons": reasons}


def run_evals(client):
    """Run every seeded eval case; return per-case results and a summary."""
    results = []
    for case in EVAL_CASES:
        trajectory = run_investigation(case["question"], client)
        judgement = judge_trajectory(trajectory)
        missing = [fact for fact in case["must_contain"]
                   if fact.lower() not in trajectory["answer"].lower()]
        case_passed = judgement["passed"] and not missing
        results.append({
            "question": case["question"],
            "passed": case_passed,
            "judge_mean": judgement["mean"],
            "missing_facts": missing,
            "reasons": judgement["reasons"],
        })
    passed = sum(1 for r in results if r["passed"])
    return {"cases": results, "passed": passed, "total": len(results),
            "pass_rate": round(passed / len(results), 3) if results else 0.0}


def monitor(runs):
    """Monitor run-over-run health.

    runs: list of {"pass_rate": float, "mean_latency_ms": float}.
    Alerts when the latest pass rate falls below 0.8, or when latency
    grew more than 10% against the previous run.
    """
    if not runs:
        return {"alert": False, "reason": "no runs to monitor"}
    latest = runs[-1]
    alerts = []
    if latest["pass_rate"] < 0.8:
        alerts.append(f"pass rate {latest['pass_rate']} below 0.8 floor")
    if len(runs) > 1:
        prev = runs[-2]["mean_latency_ms"]
        if prev > 0 and (latest["mean_latency_ms"] - prev) / prev > 0.10:
            alerts.append(
                f"latency grew {round((latest['mean_latency_ms'] - prev) / prev * 100, 1)}% "
                "over the previous run")
    return {"alert": bool(alerts), "reasons": alerts,
            "latest_pass_rate": latest["pass_rate"],
            "latest_latency_ms": latest["mean_latency_ms"]}
