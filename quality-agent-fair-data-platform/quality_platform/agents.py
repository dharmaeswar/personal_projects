"""Agentic Quality workflow: Planner -> Retriever -> Analyst -> Validator.

The agents investigate a Quality question by calling MCP tools only. The
Analyst composes its answer strictly from tool results; the Validator
recomputes every number in the answer from those same results, so an
ungrounded number is caught before the answer ships. No live LLM is
called: the agents are deterministic policies over seeded data, which
keeps every run reproducible offline.
"""

import re

from quality_platform import seed

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def plan(question):
    """Planner: turn a question into an ordered list of MCP tool steps."""
    steps = [
        {"tool": "search_data_products",
         "arguments": {"query": "batch release"},
         "purpose": "find the FAIR product that holds release data"},
        {"tool": "get_quality_metrics",
         "arguments": {"quarter": "Q2"},
         "purpose": "baseline release metrics for the earlier quarter"},
        {"tool": "get_quality_metrics",
         "arguments": {"quarter": "Q3"},
         "purpose": "current release metrics for the later quarter"},
    ]
    lowered = question.lower()
    if "deviation" in lowered or "why" in lowered:
        steps.append({"tool": "get_quality_metrics",
                      "arguments": {},
                      "purpose": "deviation breakdown behind the change"})
    steps.append({"tool": "run_quality_check",
                  "arguments": {"product_id": "batch-release"},
                  "purpose": "confirm the underlying data passed quality checks"})
    return steps


def retrieve(client, steps):
    """Retriever: execute each planned step through the MCP client."""
    calls = []
    for step in steps:
        try:
            result = client.call_tool(step["tool"], step["arguments"])
            calls.append({"tool": step["tool"], "arguments": step["arguments"],
                          "purpose": step["purpose"], "result": result,
                          "status": "ok"})
        except RuntimeError as exc:
            calls.append({"tool": step["tool"], "arguments": step["arguments"],
                          "purpose": step["purpose"], "result": None,
                          "status": "error", "error": str(exc)})
    return calls


def _metric(calls, quarter):
    for call in calls:
        if (call["tool"] == "get_quality_metrics" and call["status"] == "ok"
                and call["result"]["metrics"]["quarter"] == quarter):
            return call["result"]["metrics"]
    return None


def _deviations(calls):
    for call in calls:
        if (call["tool"] == "get_quality_metrics" and call["status"] == "ok"
                and call["result"]["metrics"]["quarter"] == "all"):
            return call["result"]["deviations"]
    return None


def analyse(question, calls):
    """Analyst: compose the answer from tool results only.

    Returns a dict with the answer text and the evidence numbers it used.
    If a needed figure is missing, the answer says so instead of guessing.
    """
    q2 = _metric(calls, "Q2")
    q3 = _metric(calls, "Q3")
    if q2 is None or q3 is None:
        return {"answer": "I cannot answer: release metrics for Q2 or Q3 "
                          "were not returned by the data tools.",
                "evidence": {}, "grounded": False}
    change = round(q3["mean_release_cycle_days"] - q2["mean_release_cycle_days"], 1)
    evidence = {
        "q2_mean_release_cycle_days": q2["mean_release_cycle_days"],
        "q3_mean_release_cycle_days": q3["mean_release_cycle_days"],
        "change_days": change,
        "q2_batches": q2["batches"],
        "q3_batches": q3["batches"],
        "q3_total_deviations": q3["total_deviations"],
    }
    lines = [
        f"Mean batch release cycle time rose from {q2['mean_release_cycle_days']} days "
        f"in Q2 to {q3['mean_release_cycle_days']} days in Q3, a change of {change} days, "
        f"across {q2['batches']} batches in Q2 and {q3['batches']} batches in Q3.",
    ]
    breakdown = _deviations(calls)
    if breakdown:
        top = max(breakdown["by_category"].items(), key=lambda kv: kv[1])
        evidence["top_deviation_category"] = top[0]
        evidence["top_deviation_count"] = top[1]
        evidence["total_deviations_all"] = breakdown["total"]
        lines.append(
            f"Deviations total {breakdown['total']}, led by {top[0]} "
            f"({top[1]} reports), which tracks the slower Q3 releases.")
    else:
        lines.append("No deviation breakdown was returned, so no cause is stated.")
    quality = [c for c in calls if c["tool"] == "run_quality_check"]
    if quality and quality[0]["status"] == "ok":
        passed = quality[0]["result"]["passed"]
        evidence["quality_check_passed"] = passed
        lines.append(
            "The batch-release data passed its quality checks."
            if passed else
            "The batch-release data FAILED its quality checks; treat the figures above as provisional.")
    return {"answer": " ".join(lines), "evidence": evidence, "grounded": True}


def validate(answer, calls):
    """Validator: recompute every number in the answer from tool results.

    Returns pass/fail plus the numbers that could not be verified.
    """
    q2 = _metric(calls, "Q2")
    q3 = _metric(calls, "Q3")
    breakdown = _deviations(calls)
    expected = set()
    if q2 and q3:
        expected |= {str(q2["mean_release_cycle_days"]),
                     str(q3["mean_release_cycle_days"]),
                     str(round(q3["mean_release_cycle_days"]
                               - q2["mean_release_cycle_days"], 1)),
                     str(q2["batches"]), str(q3["batches"]),
                     str(q3["total_deviations"])}
    if breakdown:
        expected.add(str(breakdown["total"]))
        top = max(breakdown["by_category"].items(), key=lambda kv: kv[1])
        expected.add(str(top[1]))
    numbers = NUMBER_RE.findall(re.sub(r"\bQ[1-4]\b", "", answer))
    unverified = [n for n in numbers if n not in expected]
    return {"passed": not unverified,
            "numbers_checked": len(numbers),
            "unverified_numbers": unverified}


def run_investigation(question, client):
    """Run the full agentic workflow and return the trajectory."""
    steps = plan(question)
    calls = retrieve(client, steps)
    analysis = analyse(question, calls)
    check = validate(analysis["answer"], calls)
    return {
        "question": question,
        "steps": steps,
        "tool_calls": calls,
        "answer": analysis["answer"],
        "evidence": analysis["evidence"],
        "validation": check,
        "passed": analysis["grounded"] and check["passed"],
    }
