"""Tests for the DAG orchestrator: order, retries, failure handling."""
import pytest

from product_analytics import db
from product_analytics.orchestration import Task, order_tasks, run_dag


def test_order_respects_dependencies():
    tasks = [
        Task("c", lambda conn: None, ("b",)),
        Task("a", lambda conn: None),
        Task("b", lambda conn: None, ("a",)),
    ]
    assert [t.name for t in order_tasks(tasks)] == ["a", "b", "c"]


def test_missing_dependency_raises():
    with pytest.raises(ValueError):
        order_tasks([Task("a", lambda conn: None, ("nope",))])


def test_cycle_raises():
    with pytest.raises(ValueError):
        order_tasks([
            Task("a", lambda conn: None, ("b",)),
            Task("b", lambda conn: None, ("a",)),
        ])


def test_failed_task_retries_once_then_skips_downstream():
    conn = db.connect()
    attempts = {"n": 0}

    def flaky(c):
        attempts["n"] += 1
        raise RuntimeError("boom")

    results = run_dag(conn, [
        Task("bad", flaky),
        Task("downstream", lambda c: None, ("bad",)),
    ])
    assert attempts["n"] == 2
    assert results == {"bad": "failed", "downstream": "skipped"}


def test_retry_succeeds_on_second_attempt():
    conn = db.connect()
    attempts = {"n": 0}

    def flaky(c):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    results = run_dag(conn, [Task("flaky", flaky)])
    assert results == {"flaky": "success"}
    assert attempts["n"] == 2
    row = conn.execute(
        "SELECT status FROM run_state WHERE task_name = 'flaky'").fetchone()
    assert row[0] == "success"
