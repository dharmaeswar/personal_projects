"""Failure diagnostics: classify a failed task run and suggest the fix."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Diagnosis:
    category: str
    likely_cause: str
    suggested_action: str
    retry_worth_it: bool


def diagnose(exit_code: int, log_tail: str, upstream_states: dict[str, str]) -> Diagnosis:
    log = log_tail.lower()
    failed_upstream = [t for t, s in upstream_states.items() if s == "failed"]
    if failed_upstream:
        return Diagnosis(
            category="upstream_failure",
            likely_cause=f"upstream task(s) failed: {', '.join(sorted(failed_upstream))}",
            suggested_action="Fix the upstream task first; this task was never given valid inputs.",
            retry_worth_it=False,
        )
    if exit_code == 137 or "oomkilled" in log or "out of memory" in log:
        return Diagnosis(
            category="out_of_memory",
            likely_cause="container was killed for exceeding its memory limit",
            suggested_action="Raise the task memory request/limit or reduce partition size, then rerun.",
            retry_worth_it=True,
        )
    if "deadlineexceeded" in log or "timed out" in log or "timeout" in log:
        return Diagnosis(
            category="timeout",
            likely_cause="task exceeded its execution deadline",
            suggested_action="Check for a slow downstream store; consider splitting the work or raising the deadline.",
            retry_worth_it=True,
        )
    if "connection refused" in log or "could not connect" in log or "name resolution" in log:
        return Diagnosis(
            category="connectivity",
            likely_cause="a downstream store or service was unreachable",
            suggested_action="Check the store's health and the pod's network/DNS before rerunning.",
            retry_worth_it=True,
        )
    if "permission" in log or "access denied" in log or "403" in log:
        return Diagnosis(
            category="permissions",
            likely_cause="the tenant's credentials do not allow this read or write",
            suggested_action="Re-check the tenant's grants for the dataset; do not retry until fixed.",
            retry_worth_it=False,
        )
    if "schema" in log or "column" in log and "not found" in log:
        return Diagnosis(
            category="schema_change",
            likely_cause="an upstream dataset changed shape (missing or renamed column)",
            suggested_action="Compare the dataset in the catalog with the task's expected inputs and update the task.",
            retry_worth_it=False,
        )
    return Diagnosis(
        category="unknown",
        likely_cause="no known failure pattern matched the log tail",
        suggested_action="Open the full task log and the run's pod events; escalate to the platform on-call if unclear.",
        retry_worth_it=False,
    )
