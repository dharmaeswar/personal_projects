"""Databricks-shaped jobs and workflows — the shape of the
enterprise data platform the posting names, without a real workspace.

A job is a small DAG of tasks with retries and data-quality checks
(row-count floors, null-rate ceilings, freshness limits). Tasks run
in dependency order, transient failures are retried, and every run
is recorded in a run history the Finance team can audit. The
"Databricks" part is the job/workflow/check vocabulary and the
run-history shape — there is no live Databricks connection here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class TransientError(Exception):
    """A retryable failure, e.g. a flaky source read."""


@dataclass
class DataQualityCheck:
    name: str
    kind: str  # row_count_min | null_rate_max | freshness_max_hours
    threshold: float
    column: str = ""

    def run(self, rows: list[dict], *, age_hours: float = 0.0) -> dict:
        if self.kind == "row_count_min":
            passed = len(rows) >= self.threshold
            detail = {"rows": len(rows), "minimum": self.threshold}
        elif self.kind == "null_rate_max":
            total = len(rows)
            nulls = sum(1 for r in rows if r.get(self.column) is None)
            rate = (nulls / total) if total else 0.0
            passed = rate <= self.threshold
            detail = {"null_rate": round(rate, 4),
                      "maximum": self.threshold}
        elif self.kind == "freshness_max_hours":
            passed = age_hours <= self.threshold
            detail = {"age_hours": age_hours,
                      "maximum": self.threshold}
        else:
            raise ValueError(f"unknown check kind: {self.kind}")
        return {"check": self.name, "kind": self.kind,
                "passed": passed, "detail": detail}


@dataclass
class JobTask:
    name: str
    handler: object = None  # callable(context) -> dict
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 2


@dataclass
class TaskRun:
    task: str
    attempt: int
    status: str  # succeeded | failed
    duration_ms: float
    result: dict = field(default_factory=dict)
    error: str = ""


class DatabricksJob:
    """A Databricks Jobs-shaped workflow: tasks + quality checks."""

    def __init__(self, name: str, tasks: list[JobTask],
                 checks: list[DataQualityCheck] | None = None) -> None:
        self.name = name
        self.tasks = {t.name: t for t in tasks}
        self.checks = checks or []
        self.run_history: list[TaskRun] = []
        unknown = {d for t in tasks for d in t.depends_on
                   if d not in self.tasks}
        if unknown:
            raise ValueError(f"unknown dependency: {sorted(unknown)}")

    def _order(self) -> list[JobTask]:
        done: set[str] = set()
        order: list[JobTask] = []
        remaining = dict(self.tasks)
        while remaining:
            ready = [t for t in remaining.values()
                     if all(d in done for d in t.depends_on)]
            if not ready:
                raise ValueError("job has a dependency cycle")
            for task in sorted(ready, key=lambda t: t.name):
                order.append(task)
                done.add(task.name)
                del remaining[task.name]
        return order

    def run(self, context: dict | None = None) -> dict:
        """Run every task in order; returns per-task results plus the
        quality-check verdicts. A task that keeps failing after its
        retries stops the job — later tasks do not run."""
        ctx = dict(context or {})
        results: dict[str, dict] = {}
        for task in self._order():
            result = self._run_task(task, ctx)
            if result.status == "failed":
                return {"job": self.name, "status": "failed",
                        "failed_task": task.name,
                        "results": results,
                        "run_history": [r.__dict__
                                        for r in self.run_history]}
            results[task.name] = result.result
            ctx[task.name] = result.result
        checks = [c.run(ctx.get("rows", []),
                        age_hours=ctx.get("age_hours", 0.0))
                  for c in self.checks]
        passed = all(c["passed"] for c in checks)
        return {"job": self.name,
                "status": "succeeded" if passed else "checks_failed",
                "results": results, "checks": checks,
                "run_history": [r.__dict__ for r in self.run_history]}

    def _run_task(self, task: JobTask, ctx: dict) -> TaskRun:
        last_error = ""
        for attempt in range(1, task.max_retries + 2):
            start = time.monotonic()
            try:
                result = task.handler(ctx)
                run = TaskRun(task.name, attempt, "succeeded",
                              (time.monotonic() - start) * 1000,
                              result=result or {})
                self.run_history.append(run)
                return run
            except TransientError as exc:
                last_error = str(exc)
                self.run_history.append(TaskRun(
                    task.name, attempt, "failed",
                    (time.monotonic() - start) * 1000, error=last_error))
        return TaskRun(task.name, task.max_retries + 1, "failed", 0.0,
                       error=last_error)
