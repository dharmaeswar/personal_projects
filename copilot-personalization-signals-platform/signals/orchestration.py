"""DAG orchestration: ingest -> validate -> batch -> quality -> publish.

Topological ordering, one retry for transient failures, and resume by
run id (a re-run with the same run id skips tasks that already
succeeded with the same inputs).
"""
from __future__ import annotations


class Task:
    def __init__(self, name, fn, depends_on=()):
        self.name = name
        self.fn = fn
        self.depends_on = tuple(depends_on)


class TransientError(Exception):
    """Retryable failure (e.g. a flaky upstream read)."""


class Orchestrator:
    def __init__(self):
        self.run_state: dict[str, dict] = {}

    def run(self, run_id: str, tasks: list[Task], context: dict) -> dict:
        """Run the DAG. Returns {task_name: result} for completed tasks."""
        state = self.run_state.setdefault(run_id, {})
        ordered = self._order(tasks)
        results: dict = {}
        for task in ordered:
            fingerprint = _fingerprint(task, context)
            if state.get(task.name) == fingerprint:
                results[task.name] = "skipped (already succeeded)"
                continue
            attempts = 0
            while True:
                attempts += 1
                try:
                    results[task.name] = task.fn(context)
                    break
                except TransientError:
                    if attempts >= 2:
                        raise
            state[task.name] = fingerprint
        return results

    @staticmethod
    def _order(tasks: list[Task]) -> list[Task]:
        by_name = {t.name: t for t in tasks}
        ordered: list[Task] = []
        visiting: set[str] = set()

        def visit(task: Task):
            if task.name in visiting:
                raise ValueError(f"cycle at task {task.name}")
            if any(t.name == task.name for t in ordered):
                return
            visiting.add(task.name)
            for dep in task.depends_on:
                if dep not in by_name:
                    raise ValueError(f"unknown dependency {dep}")
                visit(by_name[dep])
            visiting.discard(task.name)
            ordered.append(task)

        for task in tasks:
            visit(task)
        return ordered


def _fingerprint(task: Task, context: dict) -> str:
    """Cheap fingerprint: task name + the input ids it declares."""
    inputs = context.get("inputs", {}).get(task.name, "")
    return f"{task.name}:{inputs}"
