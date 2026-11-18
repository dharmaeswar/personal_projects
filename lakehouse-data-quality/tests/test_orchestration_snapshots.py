"""Tests for workflow orchestration (DAG runner) and Iceberg-style snapshots."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.orchestration import (
    DagError,
    DagRunner,
    Task,
    TransientError,
    order_tasks,
    render_run_report,
)
from lakehouse.snapshots import (
    commit_snapshot,
    current_snapshot,
    evolve_schema,
    list_snapshots,
    read_snapshot,
)


# --- DAG ordering -------------------------------------------------------

def test_order_tasks_respects_dependencies():
    tasks = [
        Task("gold", lambda c: None, depends_on=["silver"]),
        Task("silver", lambda c: None, depends_on=["bronze"]),
        Task("bronze", lambda c: None),
    ]
    assert [t.name for t in order_tasks(tasks)] == ["bronze", "silver", "gold"]


def test_order_tasks_rejects_unknown_dependency():
    with pytest.raises(DagError, match="unknown task"):
        order_tasks([Task("a", lambda c: None, depends_on=["missing"])])


def test_order_tasks_rejects_cycle():
    tasks = [
        Task("a", lambda c: None, depends_on=["b"]),
        Task("b", lambda c: None, depends_on=["a"]),
    ]
    with pytest.raises(DagError, match="cycle"):
        order_tasks(tasks)


def test_runner_runs_in_dependency_order(tmp_path):
    seen: list[str] = []

    def record(name):
        def fn(context):
            seen.append(name)
        return fn

    tasks = [
        Task("report", record("report"), depends_on=["gold"]),
        Task("gold", record("gold"), depends_on=["silver"]),
        Task("silver", record("silver"), depends_on=["bronze"]),
        Task("bronze", record("bronze")),
    ]
    result = DagRunner(tasks, tmp_path / "state.json").run({}, run_id="r1")
    assert result.succeeded
    assert seen == ["bronze", "silver", "gold", "report"]
    assert all(t.status == "succeeded" for t in result.tasks)


def test_runner_retries_transient_failure(tmp_path):
    calls = {"n": 0}

    def flaky(context):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientError("source hiccup")

    result = DagRunner(
        [Task("bronze", flaky, max_retries=2)], tmp_path / "state.json"
    ).run({}, run_id="r1")
    assert result.succeeded
    assert calls["n"] == 2
    assert result.tasks[0].attempts == 2


def test_runner_gives_up_after_retries_and_skips_downstream(tmp_path):
    def always_fails(context):
        raise TransientError("source down")

    tasks = [
        Task("bronze", always_fails, max_retries=1),
        Task("silver", lambda c: None, depends_on=["bronze"]),
    ]
    result = DagRunner(tasks, tmp_path / "state.json").run({}, run_id="r1")
    assert not result.succeeded
    assert result.tasks[0].status == "failed"
    assert result.tasks[0].attempts == 2
    assert result.tasks[1].status == "not_run"


def test_runner_does_not_retry_non_transient_errors(tmp_path):
    calls = {"n": 0}

    def bad(context):
        calls["n"] += 1
        raise ValueError("bad input")

    result = DagRunner(
        [Task("bronze", bad, max_retries=3)], tmp_path / "state.json"
    ).run({}, run_id="r1")
    assert not result.succeeded
    assert calls["n"] == 1
    assert "ValueError: bad input" in result.tasks[0].error


def test_runner_resumes_and_skips_unchanged_tasks(tmp_path):
    calls = {"n": 0}

    def work(context):
        calls["n"] += 1

    tasks = [Task("bronze", work)]
    context = {"inputs": {"bronze": {"source": "seed-42"}}}
    runner = DagRunner(tasks, tmp_path / "state.json")
    first = runner.run(context, run_id="r1")
    assert first.tasks[0].status == "succeeded"
    second = runner.run(context, run_id="r1")
    assert second.tasks[0].status == "skipped"
    assert calls["n"] == 1  # not re-run
    changed = {"inputs": {"bronze": {"source": "seed-43"}}}
    third = runner.run(changed, run_id="r1")
    assert third.tasks[0].status == "succeeded"
    assert calls["n"] == 2  # changed input re-runs the task


def test_run_report_names_failed_tasks(tmp_path):
    def boom(context):
        raise TransientError("nope")

    result = DagRunner(
        [Task("bronze", boom, max_retries=0)], tmp_path / "state.json"
    ).run({}, run_id="r1")
    report = render_run_report(result)
    assert "FAILED" in report
    assert "bronze: failed" in report


# --- Snapshots ----------------------------------------------------------

@pytest.fixture
def orders_df():
    return pd.DataFrame(
        {
            "order_id": ["o1", "o2"],
            "total_amount": [10.0, 20.0],
        }
    )


def test_snapshot_chain_links_parents(tmp_path, orders_df):
    first = commit_snapshot(orders_df, tmp_path, "bronze ingest")
    second = commit_snapshot(orders_df, tmp_path, "silver clean")
    assert first["snapshot_id"] == 1
    assert first["parent_id"] is None
    assert second["snapshot_id"] == 2
    assert second["parent_id"] == 1
    assert [s["snapshot_id"] for s in list_snapshots(tmp_path)] == [1, 2]


def test_time_travel_reads_old_snapshot(tmp_path, orders_df):
    commit_snapshot(orders_df, tmp_path, "v1")
    changed = orders_df.copy()
    changed.loc[0, "total_amount"] = 99.0
    commit_snapshot(changed, tmp_path, "v2")
    old = read_snapshot(tmp_path, 1)
    assert old.loc[0, "total_amount"] == 10.0
    new = read_snapshot(tmp_path, 2)
    assert new.loc[0, "total_amount"] == 99.0
    assert current_snapshot(tmp_path)["snapshot_id"] == 2


def test_read_snapshot_rejects_unknown_id(tmp_path, orders_df):
    commit_snapshot(orders_df, tmp_path, "v1")
    with pytest.raises(ValueError, match="no snapshot 7"):
        read_snapshot(tmp_path, 7)


def test_schema_evolution_adds_column_and_keeps_history(tmp_path, orders_df):
    commit_snapshot(orders_df, tmp_path, "v1")
    entry = evolve_schema(
        orders_df, tmp_path, "channel", "online", "add channel column"
    )
    assert entry["schema_version"] == 2
    assert entry["snapshot_id"] == 2
    evolved = read_snapshot(tmp_path, 2)
    assert list(evolved["channel"]) == ["online", "online"]
    old = read_snapshot(tmp_path, 1)
    assert "channel" not in old.columns  # history is never rewritten


def test_schema_evolution_rejects_duplicate_column(tmp_path, orders_df):
    commit_snapshot(orders_df, tmp_path, "v1")
    with pytest.raises(ValueError, match="already exists"):
        evolve_schema(orders_df, tmp_path, "order_id", "x", "bad evolve")
    assert len(list_snapshots(tmp_path)) == 1  # failed evolve commits nothing
