"""Evaluation infrastructure: versioned task sets, graders, failure analysis.

This is the eval-harness half of the project, mirroring the Reddit role's
"evaluation infrastructure ... versioned task sets, automated checks,
human-reviewed examples, regression reports, and release gates":

- TASK_SETS are versioned (v1). A case pins the question, the reference
  SQL, its category, and whether a human reviewed it.
- Graders are explicit about their limits: exact-result matching can fail
  on ties (see GRADER_LIMITATIONS), and the groundedness grader only
  checks that numbers in the summary appear in the result rows.
- Failure analysis groups failures by mode (translation, execution,
  validation, wrong result) instead of a bare pass/fail count.
- The failure-handling case (unknown community) is scored separately: the
  agent passes it only by reporting the task incomplete, never by
  inventing an answer.
"""

from __future__ import annotations

import re

from .agent import AnalyticsAgent

TASK_SET_VERSION = "v1"

# Each case: id, question, reference SQL (the expected answer), category,
# human_reviewed. Expected rows are computed by running the reference SQL
# against the same seeded sandbox, so the grader compares like with like.
TASK_SET_V1 = [
    {"id": "top-communities-7d",
     "question": "Which 3 communities have the most posts in the last 7 days?",
     "reference_sql": (
         "SELECT community, COUNT(*) AS post_count FROM posts "
         "WHERE created_day >= 23 GROUP BY community "
         "ORDER BY post_count DESC, community ASC LIMIT 3"),
     "category": "ranking", "human_reviewed": True},
    {"id": "avg-score-datascience",
     "question": "What is the average score of posts in datascience?",
     "reference_sql": (
         "SELECT AVG(score) AS avg_score FROM posts "
         "WHERE community = 'datascience'"),
     "category": "aggregation", "human_reviewed": True},
    {"id": "post-count-ml-14d",
     "question": "How many posts did machinelearning have in the last 14 days?",
     "reference_sql": (
         "SELECT COUNT(*) AS post_count FROM posts "
         "WHERE community = 'machinelearning' AND created_day >= 16"),
     "category": "aggregation", "human_reviewed": True},
    {"id": "highest-avg-score",
     "question": "Which community has the highest average score with at least 5 posts?",
     "reference_sql": (
         "SELECT community, AVG(score) AS avg_score FROM posts "
         "GROUP BY community HAVING COUNT(*) >= 5 "
         "ORDER BY avg_score DESC LIMIT 1"),
     "category": "ranking", "human_reviewed": True},
    {"id": "total-comments-python-7d",
     "question": "What is the total comments across all posts in python in the last 7 days?",
     "reference_sql": (
         "SELECT SUM(comments) AS total_comments FROM posts "
         "WHERE community = 'python' AND created_day >= 23"),
     "category": "aggregation", "human_reviewed": False},
    {"id": "posts-per-day-datascience-3d",
     "question": "How many posts per day did datascience have in the last 3 days?",
     "reference_sql": (
         "SELECT created_day, COUNT(*) AS post_count FROM posts "
         "WHERE community = 'datascience' AND created_day >= 27 "
         "GROUP BY created_day ORDER BY created_day ASC"),
     "category": "time-series", "human_reviewed": True},
    {"id": "top-posts-ml",
     "question": "List the 5 highest-scored posts in machinelearning.",
     "reference_sql": (
         "SELECT id, title, score FROM posts "
         "WHERE community = 'machinelearning' "
         "ORDER BY score DESC LIMIT 5"),
     "category": "ranking", "human_reviewed": False},
    {"id": "total-score-python",
     "question": "What is the total score of all posts in python?",
     "reference_sql": (
         "SELECT SUM(score) AS total_score FROM posts "
         "WHERE community = 'python'"),
     "category": "aggregation", "human_reviewed": True},
]

# Scored separately: the agent must NOT answer this. Passing means it
# reported the task incomplete with a clear reason.
FAILURE_HANDLING_CASE = {
    "id": "unknown-community",
    "question": "What is the average score of posts in quantumcomputing?",
    "category": "failure-handling",
    "human_reviewed": True,
}

GRADER_LIMITATIONS = [
    "Exact-result matching fails on ties: two different orderings of equal "
    "counts are both correct, but the grader counts the tie-break order as "
    "part of the answer. Reference SQL pins the tie-break (community ASC).",
    "The groundedness grader only checks that numbers in the summary appear "
    "in the result rows; it cannot tell whether the summary states the "
    "right conclusion from those numbers.",
    "Float averages are compared with rounding to 6 decimals; a different "
    "but equally valid rounding would fail the grader.",
]


def _rows_equal(actual, expected):
    if len(actual) != len(expected):
        return False
    for a_row, e_row in zip(actual, expected):
        if len(a_row) != len(e_row):
            return False
        for a, e in zip(a_row, e_row):
            if isinstance(a, float) or isinstance(e, float):
                if abs(float(a) - float(e)) > 1e-6:
                    return False
            elif a != e:
                return False
    return True


def grade_groundedness(summary: str, rows: list, question: str = "") -> dict:
    """Every number in the summary must appear in the result rows.

    Numbers that come from the question itself ("last 7 days", "top 3")
    and the row-count phrasing are not claims about the data, so they are
    stripped before checking.
    """
    body = summary or ""
    if question and body.startswith(question):
        body = body[len(question):]
    body = re.sub(r"Based on \d+ row\(s\)\.", "", body)
    numbers = set(re.findall(r"\d+(?:\.\d+)?", body))
    row_values = set()
    for row in rows:
        for value in row:
            if isinstance(value, (int, float)):
                row_values.add(str(value))
                row_values.add(f"{value:.2f}")
    missing = sorted(n for n in numbers if n not in row_values)
    return {"grounded": not missing, "missing_numbers": missing}


def run_eval_set(agent: AnalyticsAgent, sandbox, task_set=None) -> dict:
    """Run the agent over the versioned task set; return per-case results."""
    task_set = task_set if task_set is not None else TASK_SET_V1
    cases = []
    for case in task_set:
        expected = sandbox.run_query(case["reference_sql"])
        result = agent.answer(case["question"])
        passed = (
            result.status == "complete"
            and _rows_equal(result.rows, expected["rows"])
        )
        grounded = grade_groundedness(result.summary, result.rows,
                                      case["question"]) \
            if result.status == "complete" else {"grounded": False,
                                                  "missing_numbers": []}
        failure_mode = None
        if not passed:
            if result.status != "complete":
                failure_mode = "execution" if "execution" in (
                    result.failure_reason or "") else "translation"
            else:
                failure_mode = "wrong-result"
        cases.append({
            "id": case["id"],
            "category": case["category"],
            "human_reviewed": case["human_reviewed"],
            "passed": passed,
            "grounded": grounded["grounded"],
            "failure_mode": failure_mode,
            "failure_reason": result.failure_reason,
            "sql": result.sql,
            "latency_ms": round(sum(c["latency_ms"] for c in result.tool_calls), 2),
            "cost_usd": round(sum(c["cost_usd"] for c in result.tool_calls), 4),
        })
    # Failure-handling case: pass only if the agent declined to answer.
    fh = agent.answer(FAILURE_HANDLING_CASE["question"])
    fh_passed = fh.status == "incomplete" and fh.summary is None \
        and fh.rows == []
    passed_count = sum(1 for c in cases if c["passed"])
    return {
        "task_set_version": TASK_SET_VERSION,
        "cases": cases,
        "pass_count": passed_count,
        "total": len(cases),
        "pass_rate": passed_count / len(cases) if cases else 0.0,
        "failure_handling": {
            "id": FAILURE_HANDLING_CASE["id"],
            "passed": fh_passed,
            "failure_reason": fh.failure_reason,
        },
        "failure_modes": _failure_mode_counts(cases),
        "grader_limitations": GRADER_LIMITATIONS,
    }


def _failure_mode_counts(cases):
    counts = {}
    for case in cases:
        if case["failure_mode"]:
            counts[case["failure_mode"]] = counts.get(case["failure_mode"], 0) + 1
    return counts
