"""Orchestration: Airflow-style DAG with retries and run state.

Tasks run in dependency order; a failed task retries once, then the DAG
stops and downstream tasks are skipped. Every attempt is recorded in
run_state so a run can be audited after the fact.

Spark/Databricks mapping: each task is a Databricks Workflows job step;
the DAG itself is the Airflow definition (Composer on GCP / MWAA on AWS).
"""

from __future__ import annotations


class DagTask:
    """One DAG node: a named callable plus its upstream dependencies."""

    def __init__(self, name: str, fn, depends_on: tuple[str, ...] = ()):
        self.name = name
        self.fn = fn
        self.depends_on = depends_on


def topological_order(tasks: list[DagTask]) -> list[str]:
    """Kahn's algorithm; raises ValueError on a cycle or unknown dependency."""
    names = {task.name for task in tasks}
    for task in tasks:
        for dep in task.depends_on:
            if dep not in names:
                raise ValueError(f"task {task.name} depends on unknown task {dep}")
    remaining = {task.name: set(task.depends_on) for task in tasks}
    order: list[str] = []
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError("cycle detected in DAG dependencies")
        for name in ready:
            order.append(name)
            del remaining[name]
            for deps in remaining.values():
                deps.discard(name)
    return order


def run_dag(tasks: list[DagTask], context: dict) -> dict:
    """Run the DAG: one retry per failed task, skip downstream on failure."""
    order = topological_order(tasks)
    by_name = {task.name: task for task in tasks}
    run_state: dict[str, dict] = {}
    failed: set[str] = set()
    for name in order:
        task = by_name[name]
        if any(dep in failed for dep in task.depends_on):
            run_state[name] = {"status": "skipped", "attempts": 0,
                               "reason": "upstream failed"}
            failed.add(name)
            continue
        attempts = 0
        error: str | None = None
        while attempts < 2:
            attempts += 1
            try:
                task.fn(context)
                error = None
                break
            except Exception as exc:  # noqa: BLE001 - recorded, then retried
                error = str(exc)
        if error is None:
            run_state[name] = {"status": "success", "attempts": attempts}
        else:
            run_state[name] = {"status": "failed", "attempts": attempts,
                               "error": error}
            failed.add(name)
    return {"order": order, "tasks": run_state,
            "success": not failed}
