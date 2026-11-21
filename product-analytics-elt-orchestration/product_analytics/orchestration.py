"""A small DAG orchestrator: tasks, dependencies, retries, run state.

Each pipeline step is a task with named dependencies. The runner orders
tasks topologically, runs each one, retries a failed task once, records
every attempt in ``run_state``, and stops downstream tasks when a task
fails twice. It is deliberately small — the point is the dependency and
retry behaviour, not a scheduler.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

MAX_ATTEMPTS = 2


class Task:
    def __init__(self, name: str, fn, depends_on: tuple[str, ...] = ()):
        self.name = name
        self.fn = fn
        self.depends_on = depends_on


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record(conn: sqlite3.Connection, name: str, status: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO run_state (task_name, status, started_at, ended_at, detail) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(task_name) DO UPDATE SET status=excluded.status, "
        "started_at=excluded.started_at, ended_at=excluded.ended_at, detail=excluded.detail",
        (name, status, _now(), _now(), detail),
    )
    conn.commit()


def order_tasks(tasks: list[Task]) -> list[Task]:
    """Topological order; raises ValueError on a missing dependency or cycle."""
    by_name = {t.name: t for t in tasks}
    ordered: list[Task] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(task: Task) -> None:
        if task.name in done:
            return
        if task.name in visiting:
            raise ValueError(f"dependency cycle involving {task.name}")
        visiting.add(task.name)
        for dep in task.depends_on:
            if dep not in by_name:
                raise ValueError(f"task {task.name} depends on unknown task {dep}")
            visit(by_name[dep])
        visiting.discard(task.name)
        done.add(task.name)
        ordered.append(task)

    for task in tasks:
        visit(task)
    return ordered


def run_dag(conn: sqlite3.Connection, tasks: list[Task]) -> dict:
    """Run tasks in dependency order with one retry each. Returns a summary."""
    results: dict[str, str] = {}
    for task in order_tasks(tasks):
        if any(results.get(d) != "success" for d in task.depends_on):
            results[task.name] = "skipped"
            _record(conn, task.name, "skipped", "upstream task failed")
            continue
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                detail = task.fn(conn)
                results[task.name] = "success"
                _record(conn, task.name, "success", str(detail))
                break
            except Exception as exc:  # noqa: BLE001 - record and retry once
                last_error = str(exc)
                if attempt == MAX_ATTEMPTS:
                    results[task.name] = "failed"
                    _record(conn, task.name, "failed", last_error)
    return results
