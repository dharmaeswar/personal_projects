"""Audit trails and reproducible run artifacts.

Every agent run writes a run record: run id, dataset version, the question,
the SQL and its hash, the tool trace, and the eval outcome. A reviewer can
re-run the same question against the same dataset version and get the same
rows — that is what "reproducible artifacts" means here.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid


def run_record(question: str, result, dataset_version: str) -> dict:
    """Build the audit record for one agent run."""
    sql_hash = hashlib.sha256(
        (result.sql or "").encode()).hexdigest()[:12] if result.sql else None
    return {
        "run_id": uuid.uuid4().hex[:8],
        "dataset_version": dataset_version,
        "question": question,
        "status": result.status,
        "sql": result.sql,
        "sql_hash": sql_hash,
        "columns": result.columns,
        "rows": result.rows,
        "summary": result.summary,
        "failure_reason": result.failure_reason,
        "provenance": result.provenance,
        "tool_calls": result.tool_calls,
    }


def write_artifact(record: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)


def render_report(results: dict, gate: dict) -> str:
    """Plain-text regression report for the eval run."""
    lines = [
        f"Analytics Agent Eval Report — task set {results['task_set_version']}",
        f"Pass: {results['pass_count']}/{results['total']} "
        f"({results['pass_rate']:.1%})",
        f"Release gate: {gate['gate']}",
    ]
    if gate["reasons"]:
        lines.append("Gate reasons:")
        lines.extend(f"  - {r}" for r in gate["reasons"])
    fh = results["failure_handling"]
    lines.append(
        f"Failure handling ({fh['id']}): "
        f"{'PASS' if fh['passed'] else 'FAIL'} — {fh['failure_reason']}")
    if results["failure_modes"]:
        lines.append(f"Failure modes: {results['failure_modes']}")
    lines.append("Cases:")
    for case in results["cases"]:
        mark = "PASS" if case["passed"] else "FAIL"
        grounded = "grounded" if case["grounded"] else "UNGROUNDED"
        lines.append(
            f"  [{mark}] {case['id']} ({case['category']}, "
            f"human-reviewed={case['human_reviewed']}, {grounded}, "
            f"{case['latency_ms']}ms, ${case['cost_usd']})")
        if case["failure_reason"]:
            lines.append(f"        {case['failure_reason']}")
    lines.append("Grader limitations:")
    lines.extend(f"  - {limit}" for limit in results["grader_limitations"])
    return "\n".join(lines) + "\n"
