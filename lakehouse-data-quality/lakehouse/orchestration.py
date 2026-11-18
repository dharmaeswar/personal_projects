"""Minimal workflow orchestration for the lakehouse pipeline.

A small DAG runner in the spirit of Airflow: each pipeline stage is a
Task with named upstream dependencies, the runner topologically sorts
them, runs them in order, retries a task that raises a transient error,
and records a run state file so a re-run resumes (skips tasks that
already succeeded with the same inputs) instead of redoing the work.
A failed task marks the run failed and its downstream tasks are skipped,
never run on stale inputs.

This runs locally with plain Python — no scheduler service is involved —
so the same DAG maps one-to-one onto an Airflow DAG: each Task becomes
an operator, ``depends_on`` becomes ``>>`` / ``set_upstream``, and the
run-state file becomes the scheduler's task-instance state.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class DagError(ValueError):
    """Raised for an invalid DAG: unknown dependency or a cycle."""


class TransientError(RuntimeError):
    """Raised by a task to signal a retryable failure (e.g. a flaky source)."""


@dataclass
class Task:
    """One pipeline stage. ``fn`` receives the shared context dict."""

    name: str
    fn: Callable[[dict], object]
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 1

    def fingerprint(self, context: dict) -> str:
        """Hash of the task name + the context keys it reads.

        Tasks declare their inputs in ``context["inputs"]``; a re-run with
        identical inputs skips the task, a changed input re-runs it.
        """
        inputs = context.get("inputs", {}).get(self.name, {})
        payload = json.dumps({"task": self.name, "inputs": inputs}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass
class TaskResult:
    name: str
    status: str  # "succeeded", "skipped", "failed", "not_run"
    attempts: int
    seconds: float
    error: str = ""


@dataclass
class RunResult:
    run_id: str
    succeeded: bool
    tasks: list[TaskResult]


def order_tasks(tasks: list[Task]) -> list[Task]:
    """Topologically sort tasks; raise DagError on unknown deps or cycles."""
    by_name = {t.name: t for t in tasks}
    for task in tasks:
        for dep in task.depends_on:
            if dep not in by_name:
                raise DagError(f"task {task.name!r} depends on unknown task {dep!r}")
    ordered: list[Task] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task: Task) -> None:
        if task.name in visited:
            return
        if task.name in visiting:
            raise DagError(f"dependency cycle involving task {task.name!r}")
        visiting.add(task.name)
        for dep in task.depends_on:
            visit(by_name[dep])
        visiting.discard(task.name)
        visited.add(task.name)
        ordered.append(task)

    for task in tasks:
        visit(task)
    return ordered


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text())


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True))


class DagRunner:
    """Runs a list of Tasks in dependency order with retries and resume."""

    def __init__(self, tasks: list[Task], state_path: Path | str):
        self.tasks = order_tasks(tasks)
        self.state_path = Path(state_path)

    def run(self, context: dict, run_id: str) -> RunResult:
        state = _load_state(self.state_path)
        prior = state.get("runs", {}).get(run_id, {})
        results: list[TaskResult] = []
        failed: set[str] = set()
        for task in self.tasks:
            if any(dep in failed for dep in task.depends_on):
                results.append(TaskResult(task.name, "not_run", 0, 0.0, "upstream task failed"))
                continue
            fingerprint = task.fingerprint(context)
            if prior.get(task.name, {}).get("fingerprint") == fingerprint:
                results.append(TaskResult(task.name, "skipped", 0, 0.0, "already succeeded with same inputs"))
                continue
            started = time.monotonic()
            attempts = 0
            error = ""
            while True:
                attempts += 1
                try:
                    task.fn(context)
                    error = ""
                    break
                except TransientError as exc:
                    error = str(exc)
                    if attempts > task.max_retries:
                        break
                    time.sleep(0)  # no backoff delay in local runs; retries are immediate
                except Exception as exc:  # non-transient: do not retry
                    error = f"{type(exc).__name__}: {exc}"
                    break
            seconds = time.monotonic() - started
            succeeded = error == ""
            if succeeded:
                prior[task.name] = {"fingerprint": fingerprint, "status": "succeeded"}
                results.append(TaskResult(task.name, "succeeded", attempts, seconds))
            else:
                failed.add(task.name)
                results.append(TaskResult(task.name, "failed", attempts, seconds, error))
        state.setdefault("runs", {})[run_id] = prior
        _save_state(self.state_path, state)
        return RunResult(run_id, not failed, results)


def render_run_report(result: RunResult) -> str:
    """One-line-per-task summary of a DAG run, for the run report."""
    lines = [f"DAG RUN {result.run_id}: {'SUCCEEDED' if result.succeeded else 'FAILED'}"]
    for task in result.tasks:
        detail = f"{task.name}: {task.status} ({task.attempts} attempt(s), {task.seconds:.2f}s)"
        if task.error:
            detail += f" — {task.error}"
        lines.append(detail)
    return "\n".join(lines) + "\n"
